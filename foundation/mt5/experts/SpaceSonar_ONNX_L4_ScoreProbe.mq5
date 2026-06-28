//+------------------------------------------------------------------+
//| SpaceSonar ONNX L4 Score Probe                                   |
//| Non-trading EA: full-period feature -> ONNX score -> decision log.|
//+------------------------------------------------------------------+
#property strict
#property version   "1.02"
#property description "Non-trading full-period ONNX score probe for SpaceSonar X L4."

#include <Trade/Trade.mqh>

input string InpOnnxPath       = "SpaceSonar\\l4_score_probe\\bundle\\model.onnx";
input string InpOutputPath     = "SpaceSonar\\l4_score_probe\\attempt\\score_telemetry.csv";
input string InpDiagnosticPath = "";
input string InpFeatureColumns = "";
input string InpFeatureColumnsPath = "";
input int    InpFeatureCount   = 0;
input string InpInputFamily    = "";
input string InpDecisionFamily = "";
input double InpScoreLow       = 0.0;
input double InpScoreHigh      = 0.0;
input bool   InpHasLowHigh     = false;
input int    InpHistoryBars    = 600;
input int    InpMaxRows        = 0;
input bool   InpUseCommonFiles = true;
input double InpFixedLot       = 0.02;
input bool   InpExecuteTrades  = false;
input int    InpHoldBars       = 72;
input ulong  InpMagicNumber    = 503015;
input int    InpDeviationPoints = 20;
input int    InpBarTimeToUtcOffsetHours = 0;

#define SPACESONAR_PI 3.14159265358979323846

long     ExtOnnxHandle = INVALID_HANDLE;
int      ExtOutputHandle = INVALID_HANDLE;
int      ExtDiagnosticHandle = INVALID_HANDLE;
datetime ExtLastClosedBarTime = 0;
int      ExtRowsWritten = 0;
int      ExtTicksSeen = 0;
int      ExtClosedBarCandidates = 0;
int      ExtFeatureFailureCount = 0;
int      ExtOnnxFailureCount = 0;
bool     ExtMaxRowsReachedLogged = false;
string   ExtColumns[];
CTrade   ExtTrade;
int      ExtBarsSinceEntry = 0;

string DiagnosticTime(const datetime value)
{
   if(value <= 0)
      return "";
   return TimeToString(value, TIME_DATE | TIME_SECONDS);
}

bool ShouldLogSample(const int count)
{
   return (count <= 20 || (count % 1000) == 0);
}

void WriteDiagnosticEvent(const string event_name, const datetime bar_time, const string detail)
{
   if(ExtDiagnosticHandle == INVALID_HANDLE)
      return;

   const int last_error = GetLastError();
   FileWrite(ExtDiagnosticHandle,
             TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS),
             event_name,
             DiagnosticTime(bar_time),
             _Symbol,
             EnumToString(_Period),
             detail,
             last_error,
             ExtRowsWritten,
             ExtTicksSeen,
             ExtClosedBarCandidates,
             ExtFeatureFailureCount,
             ExtOnnxFailureCount);
   FileFlush(ExtDiagnosticHandle);
}

void OpenDiagnosticLog()
{
   if(StringLen(InpDiagnosticPath) <= 0)
      return;

   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   ExtDiagnosticHandle = FileOpen(InpDiagnosticPath, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(ExtDiagnosticHandle == INVALID_HANDLE)
   {
      PrintFormat("SpaceSonar L4 diagnostic open failed path=%s err=%d", InpDiagnosticPath, GetLastError());
      return;
   }
   FileWrite(ExtDiagnosticHandle,
             "event_time",
             "event",
             "bar_time",
             "symbol",
             "period",
             "detail",
             "last_error",
             "rows_written",
             "ticks_seen",
             "closed_bar_candidates",
             "feature_failures",
             "onnx_failures");
   FileFlush(ExtDiagnosticHandle);
}

double SafeDiv(const double numerator, const double denominator)
{
   if(denominator == 0.0 || !MathIsValidNumber(denominator))
      return 0.0;
   return numerator / denominator;
}

bool IsFinite(const double value)
{
   return MathIsValidNumber(value);
}

double CloseAt(const MqlRates &rates[], const int index)
{
   return rates[index].close;
}

double RetAt(const MqlRates &rates[], const int index, const int window)
{
   const int prev = index - window;
   if(prev < 0)
      return 0.0;
   return SafeDiv(rates[index].close - rates[prev].close, rates[prev].close);
}

double RangePctAt(const MqlRates &rates[], const int index)
{
   return SafeDiv(rates[index].high - rates[index].low, rates[index].close);
}

double TrueRangeAt(const MqlRates &rates[], const int index)
{
   const double previous_close = (index > 0 ? rates[index - 1].close : rates[index].close);
   const double range_high_low = rates[index].high - rates[index].low;
   const double range_high_close = MathAbs(rates[index].high - previous_close);
   const double range_low_close = MathAbs(rates[index].low - previous_close);
   return MathMax(range_high_low, MathMax(range_high_close, range_low_close));
}

bool MeanClose(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      sum += rates[i].close;
      count++;
   }
   if(count < min_count)
      return false;
   mean = sum / (double)count;
   return true;
}

bool MeanRange(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      sum += RangePctAt(rates, i);
      count++;
   }
   if(count < min_count)
      return false;
   mean = sum / (double)count;
   return true;
}

bool MeanStdRange(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean, double &std_value)
{
   double values[];
   ArrayResize(values, 0);
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      const int size = ArraySize(values);
      ArrayResize(values, size + 1);
      values[size] = RangePctAt(rates, i);
   }
   const int count = ArraySize(values);
   if(count < min_count)
      return false;
   double sum = 0.0;
   for(int i = 0; i < count; i++)
      sum += values[i];
   mean = sum / (double)count;
   if(count < 2)
   {
      std_value = 0.0;
      return true;
   }
   double ss = 0.0;
   for(int i = 0; i < count; i++)
      ss += MathPow(values[i] - mean, 2.0);
   std_value = MathSqrt(ss / (double)(count - 1));
   return true;
}

bool MeanTrueRange(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      sum += TrueRangeAt(rates, i);
      count++;
   }
   if(count < min_count)
      return false;
   mean = sum / (double)count;
   return true;
}

bool MeanSpreadScaled(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      sum += ((double)rates[i].spread) / 1000.0;
      count++;
   }
   if(count < min_count)
      return false;
   mean = sum / (double)count;
   return true;
}

bool MeanStdSpreadPoints(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean, double &std_value)
{
   double values[];
   ArrayResize(values, 0);
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      const int size = ArraySize(values);
      ArrayResize(values, size + 1);
      values[size] = (double)rates[i].spread;
   }
   const int count = ArraySize(values);
   if(count < min_count)
      return false;
   double sum = 0.0;
   for(int i = 0; i < count; i++)
      sum += values[i];
   mean = sum / (double)count;
   if(count < 2)
   {
      std_value = 0.0;
      return true;
   }
   double ss = 0.0;
   for(int i = 0; i < count; i++)
      ss += MathPow(values[i] - mean, 2.0);
   std_value = MathSqrt(ss / (double)(count - 1));
   return true;
}

bool SpreadRankPct(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   const int start = MathMax(0, index - window + 1);
   const int count = index - start + 1;
   if(count < min_count)
      return false;
   const double current = (double)rates[index].spread;
   int less = 0;
   int equal = 0;
   for(int i = start; i <= index; i++)
   {
      const double candidate = (double)rates[i].spread;
      if(candidate < current)
         less++;
      if(candidate == current)
         equal++;
   }
   value = ((double)less + ((double)equal + 1.0) / 2.0) / (double)count;
   return true;
}

bool TickVolumeRankPct(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   const int start = MathMax(0, index - window + 1);
   const int count = index - start + 1;
   if(count < min_count)
      return false;
   const double current = (double)rates[index].tick_volume;
   int less = 0;
   int equal = 0;
   for(int i = start; i <= index; i++)
   {
      const double candidate = (double)rates[i].tick_volume;
      if(candidate < current)
         less++;
      if(candidate == current)
         equal++;
   }
   value = ((double)less + ((double)equal + 1.0) / 2.0) / (double)count;
   return true;
}

bool RangeRankPct(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   const int start = MathMax(0, index - window + 1);
   const int count = index - start + 1;
   if(count < min_count)
      return false;
   const double current = RangePctAt(rates, index);
   int less = 0;
   int equal = 0;
   for(int i = start; i <= index; i++)
   {
      const double candidate = RangePctAt(rates, i);
      if(candidate < current)
         less++;
      if(candidate == current)
         equal++;
   }
   value = ((double)less + ((double)equal + 1.0) / 2.0) / (double)count;
   return true;
}

bool AtrPctAt(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   double mean = 0.0;
   if(!MeanTrueRange(rates, index, window, min_count, mean))
      return false;
   value = SafeDiv(mean, rates[index].close);
   return true;
}

bool AtrPctRank(const MqlRates &rates[], const int index, const int rank_window, const int rank_min_count, double &value)
{
   double current = 0.0;
   if(!AtrPctAt(rates, index, 48, 12, current))
      return false;

   const int start = MathMax(0, index - rank_window + 1);
   int count = 0;
   int less = 0;
   int equal = 0;
   for(int i = start; i <= index; i++)
   {
      double candidate = 0.0;
      if(!AtrPctAt(rates, i, 48, 12, candidate))
         continue;
      count++;
      if(candidate < current)
         less++;
      if(candidate == current)
         equal++;
   }
   if(count < rank_min_count)
      return false;
   value = ((double)less + ((double)equal + 1.0) / 2.0) / (double)count;
   return true;
}

bool MeanTickVolumeZ(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      double z = 0.0;
      if(TickVolumeZ(rates, i, 48, 12, z))
      {
         sum += z;
         count++;
      }
   }
   if(count < min_count)
      return false;
   mean = sum / (double)count;
   return true;
}

bool MeanStdRet(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean, double &std_value)
{
   double values[];
   ArrayResize(values, 0);
   for(int i = MathMax(1, index - window + 1); i <= index; i++)
   {
      const double value = RetAt(rates, i, 1);
      const int size = ArraySize(values);
      ArrayResize(values, size + 1);
      values[size] = value;
   }
   const int count = ArraySize(values);
   if(count < min_count)
      return false;
   double sum = 0.0;
   for(int i = 0; i < count; i++)
      sum += values[i];
   mean = sum / (double)count;
   if(count < 2)
   {
      std_value = 0.0;
      return true;
   }
   double ss = 0.0;
   for(int i = 0; i < count; i++)
      ss += MathPow(values[i] - mean, 2.0);
   std_value = MathSqrt(ss / (double)(count - 1));
   return true;
}

bool MeanAbsRet(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(1, index - window + 1); i <= index; i++)
   {
      sum += MathAbs(RetAt(rates, i, 1));
      count++;
   }
   if(count < min_count)
      return false;
   mean = sum / (double)count;
   return true;
}

bool SumAbsRet(const MqlRates &rates[], const int index, const int window, const int min_count, double &sum)
{
   sum = 0.0;
   int count = 0;
   for(int i = MathMax(1, index - window + 1); i <= index; i++)
   {
      sum += MathAbs(RetAt(rates, i, 1));
      count++;
   }
   return count >= min_count;
}

bool MeanStdAbsRet(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean, double &std_value)
{
   double values[];
   ArrayResize(values, 0);
   for(int i = MathMax(1, index - window + 1); i <= index; i++)
   {
      const int size = ArraySize(values);
      ArrayResize(values, size + 1);
      values[size] = MathAbs(RetAt(rates, i, 3));
   }
   const int count = ArraySize(values);
   if(count < min_count)
      return false;
   double sum = 0.0;
   for(int i = 0; i < count; i++)
      sum += values[i];
   mean = sum / (double)count;
   if(count < 2)
   {
      std_value = 0.0;
      return true;
   }
   double ss = 0.0;
   for(int i = 0; i < count; i++)
      ss += MathPow(values[i] - mean, 2.0);
   std_value = MathSqrt(ss / (double)(count - 1));
   return true;
}

bool StdClose(const MqlRates &rates[], const int index, const int window, const int min_count, double &mean, double &std_value)
{
   if(!MeanClose(rates, index, window, min_count, mean))
      return false;
   int count = 0;
   double ss = 0.0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      ss += MathPow(rates[i].close - mean, 2.0);
      count++;
   }
   std_value = (count > 1 ? MathSqrt(ss / (double)(count - 1)) : 0.0);
   return true;
}

bool TickVolumeZ(const MqlRates &rates[], const int index, const int window, const int min_count, double &z_value)
{
   double sum = 0.0;
   int count = 0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      sum += (double)rates[i].tick_volume;
      count++;
   }
   if(count < min_count)
      return false;
   const double mean = sum / (double)count;
   double ss = 0.0;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
      ss += MathPow((double)rates[i].tick_volume - mean, 2.0);
   const double std_value = (count > 1 ? MathSqrt(ss / (double)(count - 1)) : 0.0);
   z_value = SafeDiv((double)rates[index].tick_volume - mean, std_value);
   return true;
}

bool MaxHigh(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   int count = 0;
   value = -DBL_MAX;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      value = MathMax(value, rates[i].high);
      count++;
   }
   return count >= min_count;
}

bool MinLow(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   int count = 0;
   value = DBL_MAX;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      value = MathMin(value, rates[i].low);
      count++;
   }
   return count >= min_count;
}

bool MaxClose(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   int count = 0;
   value = -DBL_MAX;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      value = MathMax(value, rates[i].close);
      count++;
   }
   return count >= min_count;
}

bool MinClose(const MqlRates &rates[], const int index, const int window, const int min_count, double &value)
{
   int count = 0;
   value = DBL_MAX;
   for(int i = MathMax(0, index - window + 1); i <= index; i++)
   {
      value = MathMin(value, rates[i].close);
      count++;
   }
   return count >= min_count;
}

int MinPeriodsForWindow(const int window, const bool regime)
{
   if(regime)
      return MathMax(12, window / 6);
   return MathMax(6, window / 4);
}

bool ParseWindowSuffix(const string column, const string prefix, int &window)
{
   if(StringFind(column, prefix) != 0)
      return false;
   window = (int)StringToInteger(StringSubstr(column, StringLen(prefix)));
   return window > 0;
}

double RenderedClockFeature(const string column, const datetime close_time)
{
   MqlDateTime dt;
   TimeToStruct(close_time, dt);
   const double minute_of_day = (double)dt.hour * 60.0 + (double)dt.min;
   const double day_of_week = (double)dt.day_of_week;
   if(column == "rendered_minute_sin")
      return MathSin(2.0 * SPACESONAR_PI * minute_of_day / 1440.0);
   if(column == "rendered_minute_cos")
      return MathCos(2.0 * SPACESONAR_PI * minute_of_day / 1440.0);
   if(column == "rendered_dow_sin")
      return MathSin(2.0 * SPACESONAR_PI * day_of_week / 7.0);
   if(column == "rendered_dow_cos")
      return MathCos(2.0 * SPACESONAR_PI * day_of_week / 7.0);
   if(column == "rendered_hour")
      return (double)dt.hour;
   if(column == "rendered_is_monday")
      return (dt.day_of_week == 1 ? 1.0 : 0.0);
   if(column == "rendered_is_friday")
      return (dt.day_of_week == 5 ? 1.0 : 0.0);
   return 0.0;
}

datetime MakeUtcLikeDateTime(const int year, const int mon, const int day, const int hour, const int minute)
{
   MqlDateTime dt = {};
   dt.year = year;
   dt.mon = mon;
   dt.day = day;
   dt.hour = hour;
   dt.min = minute;
   dt.sec = 0;
   return StructToTime(dt);
}

int DayOfWeekForDate(const int year, const int mon, const int day)
{
   MqlDateTime dt;
   TimeToStruct(MakeUtcLikeDateTime(year, mon, day, 0, 0), dt);
   return dt.day_of_week;
}

int NthSundayDay(const int year, const int mon, const int nth)
{
   const int first_dow = DayOfWeekForDate(year, mon, 1);
   const int first_sunday = (first_dow == 0 ? 1 : 8 - first_dow);
   return first_sunday + (nth - 1) * 7;
}

bool IsNewYorkDstUtcLike(const datetime utc_like_time)
{
   MqlDateTime dt;
   TimeToStruct(utc_like_time, dt);
   const int year = dt.year;
   const int march_second_sunday = NthSundayDay(year, 3, 2);
   const int november_first_sunday = NthSundayDay(year, 11, 1);
   const datetime dst_start_utc = MakeUtcLikeDateTime(year, 3, march_second_sunday, 7, 0);
   const datetime dst_end_utc = MakeUtcLikeDateTime(year, 11, november_first_sunday, 6, 0);
   return (utc_like_time >= dst_start_utc && utc_like_time < dst_end_utc);
}

datetime ToNewYorkRenderedTime(const datetime close_time)
{
   const datetime utc_like_time = close_time + InpBarTimeToUtcOffsetHours * 3600;
   const int ny_offset_hours = (IsNewYorkDstUtcLike(utc_like_time) ? -4 : -5);
   return utc_like_time + ny_offset_hours * 3600;
}

bool SessionTransitionFeature(const string column, const datetime close_time, double &value)
{
   MqlDateTime dt;
   TimeToStruct(ToNewYorkRenderedTime(close_time), dt);

   const double minute = (double)dt.hour * 60.0 + (double)dt.min;
   const int python_dow = (dt.day_of_week + 6) % 7;
   const double dow = (double)python_dow;
   const double cash_open = 9.5 * 60.0;
   const double cash_close = 16.0 * 60.0;
   const double midday = 12.5 * 60.0;

   if(column == "ny_minute_sin" || column == "session_minute_sin") { value = MathSin(2.0 * SPACESONAR_PI * minute / 1440.0); return true; }
   if(column == "ny_minute_cos" || column == "session_minute_cos") { value = MathCos(2.0 * SPACESONAR_PI * minute / 1440.0); return true; }
   if(column == "ny_dow_sin" || column == "session_dow_sin") { value = MathSin(2.0 * SPACESONAR_PI * dow / 7.0); return true; }
   if(column == "ny_dow_cos" || column == "session_dow_cos") { value = MathCos(2.0 * SPACESONAR_PI * dow / 7.0); return true; }
   if(column == "minutes_from_cash_open_scaled" || column == "session_minutes_from_cash_open") { value = (minute - cash_open) / 390.0; return true; }
   if(column == "minutes_to_cash_close_scaled" || column == "session_minutes_to_cash_close") { value = (cash_close - minute) / 390.0; return true; }
   if(column == "minutes_from_midday_scaled") { value = (minute - midday) / 390.0; return true; }
   if(column == "is_pre_cash" || column == "session_is_pre_cash") { value = (minute >= 4.0 * 60.0 && minute < cash_open ? 1.0 : 0.0); return true; }
   if(column == "is_cash_session" || column == "session_is_cash") { value = (minute >= cash_open && minute <= cash_close ? 1.0 : 0.0); return true; }
   if(column == "is_after_cash" || column == "session_is_after_cash") { value = (minute > cash_close && minute <= 20.0 * 60.0 ? 1.0 : 0.0); return true; }
   if(column == "session_is_edge") { value = (MathAbs(minute - cash_open) <= 45.0 || MathAbs(minute - cash_close) <= 45.0 ? 1.0 : 0.0); return true; }
   if(column == "is_cash_open_transition" || column == "transition_cash_open_60m" || column == "session_is_open_60m") { value = (MathAbs(minute - cash_open) <= 60.0 ? 1.0 : 0.0); return true; }
   if(column == "session_is_open_90m") { value = (MathAbs(minute - cash_open) <= 90.0 ? 1.0 : 0.0); return true; }
   if(column == "is_cash_close_transition" || column == "transition_cash_close_60m" || column == "session_is_close_60m") { value = (MathAbs(minute - cash_close) <= 60.0 ? 1.0 : 0.0); return true; }
   if(column == "is_midday_block" || column == "transition_midday_90m") { value = (MathAbs(minute - midday) <= 90.0 ? 1.0 : 0.0); return true; }
   if(column == "is_monday") { value = (python_dow == 0 ? 1.0 : 0.0); return true; }
   if(column == "is_friday") { value = (python_dow == 4 ? 1.0 : 0.0); return true; }
   return false;
}

bool LocalContextFeature(const string column, const MqlRates &rates[], const int index, double &value)
{
   int window = 0;
   double mean = 0.0;

   if(ParseWindowSuffix(column, "local_ret_", window))
   {
      value = RetAt(rates, index, window);
      return true;
   }
   if(column == "local_range_pct")
   {
      value = RangePctAt(rates, index);
      return true;
   }
   if(ParseWindowSuffix(column, "local_range_mean_", window))
   {
      if(!MeanRange(rates, index, window, MinPeriodsForWindow(window, false), mean)) return false;
      value = mean;
      return true;
   }
   if(column == "local_range_ratio_12_48")
   {
      double mean12 = 0.0, mean48 = 0.0;
      if(!MeanRange(rates, index, 12, 6, mean12)) return false;
      if(!MeanRange(rates, index, 48, 12, mean48)) return false;
      value = SafeDiv(mean12, mean48);
      return true;
   }
   if(ParseWindowSuffix(column, "local_ret_abs_mean_", window))
   {
      if(!MeanAbsRet(rates, index, window, MinPeriodsForWindow(window, false), mean)) return false;
      value = mean;
      return true;
   }
   if(column == "local_ret_abs_ratio_12_48")
   {
      double mean12 = 0.0, mean48 = 0.0;
      if(!MeanAbsRet(rates, index, 12, 6, mean12)) return false;
      if(!MeanAbsRet(rates, index, 48, 12, mean48)) return false;
      value = SafeDiv(mean12, mean48);
      return true;
   }
   if(ParseWindowSuffix(column, "local_tick_volume_z_", window))
      return TickVolumeZ(rates, index, window, MinPeriodsForWindow(window, false), value);
   if(column == "local_spread_scaled")
   {
      value = ((double)rates[index].spread) / 1000.0;
      return true;
   }
   return false;
}

bool FeatureValue(const string column, const MqlRates &rates[], const int index, double &value)
{
   int window = 0;
   double mean = 0.0;
   double std_value = 0.0;

   if(column == "ret_1") { value = RetAt(rates, index, 1); return true; }
   if(column == "ret_2") { value = RetAt(rates, index, 2); return true; }
   if(column == "ret_3") { value = RetAt(rates, index, 3); return true; }
   if(column == "ret_6") { value = RetAt(rates, index, 6); return true; }
   if(column == "hl_range_pct") { value = RangePctAt(rates, index); return true; }
   if(column == "body_pct") { value = SafeDiv(rates[index].close - rates[index].open, rates[index].open); return true; }
   if(column == "upper_wick_pct")
   {
      value = SafeDiv(rates[index].high - MathMax(rates[index].open, rates[index].close), rates[index].close);
      return true;
   }
   if(column == "lower_wick_pct")
   {
      value = SafeDiv(MathMin(rates[index].open, rates[index].close) - rates[index].low, rates[index].close);
      return true;
   }
   if(column == "true_range_pct")
   {
      value = SafeDiv(TrueRangeAt(rates, index), rates[index].close);
      return true;
   }
   if(column == "atr_12_pct")
   {
      if(!MeanTrueRange(rates, index, 12, 6, mean)) return false;
      value = SafeDiv(mean, rates[index].close);
      return true;
   }
   if(column == "atr_48_pct")
   {
      if(!MeanTrueRange(rates, index, 48, 12, mean)) return false;
      value = SafeDiv(mean, rates[index].close);
      return true;
   }
   if(column == "atr_144_pct")
   {
      if(!MeanTrueRange(rates, index, 144, 36, mean)) return false;
      value = SafeDiv(mean, rates[index].close);
      return true;
   }
   if(column == "atr_12_vs_48")
   {
      double atr12 = 0.0, atr48 = 0.0;
      if(!MeanTrueRange(rates, index, 12, 6, atr12)) return false;
      if(!MeanTrueRange(rates, index, 48, 12, atr48)) return false;
      value = SafeDiv(atr12, atr48);
      return true;
   }
   if(column == "atr_48_vs_144")
   {
      double atr48 = 0.0, atr144 = 0.0;
      if(!MeanTrueRange(rates, index, 48, 12, atr48)) return false;
      if(!MeanTrueRange(rates, index, 144, 36, atr144)) return false;
      value = SafeDiv(atr48, atr144);
      return true;
   }
   if(column == "atr_rank_288" || column == "volatility_atr_rank_288")
   {
      return AtrPctRank(rates, index, 288, 72, value);
   }
   if(column == "volatility_atr_48_pct")
   {
      if(!MeanTrueRange(rates, index, 48, 12, mean)) return false;
      value = SafeDiv(mean, rates[index].close);
      return true;
   }
   if(column == "spread_scaled") { value = ((double)rates[index].spread) / 1000.0; return true; }
   if(column == "cost_spread_return_proxy")
   {
      value = SafeDiv(((double)rates[index].spread) / 100.0, rates[index].close);
      return true;
   }
   if(column == "cost_to_atr_proxy")
   {
      if(!MeanTrueRange(rates, index, 48, 12, mean)) return false;
      value = SafeDiv(((double)rates[index].spread) / 100.0, mean);
      return true;
   }
   if(column == "spread_z_48" || column == "execution_spread_z_48")
   {
      if(!MeanStdSpreadPoints(rates, index, 48, 12, mean, std_value)) return false;
      value = SafeDiv((double)rates[index].spread - mean, std_value);
      return true;
   }
   if(column == "spread_rank_144")
   {
      return SpreadRankPct(rates, index, 144, 36, value);
   }
   if(column == "execution_range_cost_ratio")
   {
      value = SafeDiv(rates[index].high - rates[index].low, ((double)rates[index].spread) / 100.0);
      return true;
   }
   if(column == "execution_gap_ret_1_vs_spread")
   {
      const double spread_cost = SafeDiv(((double)rates[index].spread) / 100.0, rates[index].close);
      value = SafeDiv(MathAbs(RetAt(rates, index, 1)), spread_cost);
      return true;
   }
   if(column == "range_pct") { value = RangePctAt(rates, index); return true; }
   if(column == "range_body_pct") { value = SafeDiv(MathAbs(rates[index].close - rates[index].open), rates[index].close); return true; }
   if(column == "range_upper_wick_pct")
   {
      value = SafeDiv(rates[index].high - MathMax(rates[index].open, rates[index].close), rates[index].close);
      return true;
   }
   if(column == "range_lower_wick_pct")
   {
      value = SafeDiv(MathMin(rates[index].open, rates[index].close) - rates[index].low, rates[index].close);
      return true;
   }
   if(column == "tick_volume_log1p") { value = MathLog(1.0 + MathMax(0.0, (double)rates[index].tick_volume)); return true; }
   if(column == "rolling_ret_mean_12")
   {
      if(!MeanStdRet(rates, index, 12, 6, mean, std_value)) return false;
      value = mean;
      return true;
   }
   if(column == "rolling_ret_std_12")
   {
      if(!MeanStdRet(rates, index, 12, 6, mean, std_value)) return false;
      value = std_value;
      return true;
   }
   if(column == "rolling_range_mean_12")
   {
      if(!MeanRange(rates, index, 12, 6, mean)) return false;
      value = mean;
      return true;
   }
   if(column == "rolling_spread_mean_12")
   {
      if(!MeanSpreadScaled(rates, index, 12, 6, mean)) return false;
      value = mean;
      return true;
   }
   if(column == "body_to_range")
   {
      const double body_pct = SafeDiv(rates[index].close - rates[index].open, rates[index].open);
      value = SafeDiv(MathAbs(body_pct), MathAbs(RangePctAt(rates, index)));
      return true;
   }
   if(ParseWindowSuffix(column, "ret_", window))
   {
      value = RetAt(rates, index, window);
      return true;
   }
   if(ParseWindowSuffix(column, "ret_mean_", window))
   {
      if(!MeanStdRet(rates, index, window, MinPeriodsForWindow(window, false), mean, std_value)) return false;
      value = mean;
      return true;
   }
   if(ParseWindowSuffix(column, "ret_std_", window))
   {
      if(!MeanStdRet(rates, index, window, MinPeriodsForWindow(window, false), mean, std_value)) return false;
      value = std_value;
      return true;
   }
   if(ParseWindowSuffix(column, "realized_vol_", window))
   {
      if(!MeanStdRet(rates, index, window, MathMax(4, window / 4), mean, std_value)) return false;
      value = std_value;
      return true;
   }
   if(ParseWindowSuffix(column, "range_mean_", window))
   {
      if(!MeanRange(rates, index, window, MinPeriodsForWindow(window, false), mean)) return false;
      value = mean;
      return true;
   }
   if(ParseWindowSuffix(column, "range_std_", window))
   {
      if(!MeanStdRange(rates, index, window, MinPeriodsForWindow(window, false), mean, std_value)) return false;
      value = std_value;
      return true;
   }
   if(ParseWindowSuffix(column, "range_rank_", window))
   {
      return RangeRankPct(rates, index, window, MathMax(4, window / 4), value);
   }
   if(ParseWindowSuffix(column, "path_abs_ret_mean_", window))
   {
      int min_periods = MathMax(1, window / 4);
      if(min_periods > window)
         min_periods = window;
      if(!MeanAbsRet(rates, index, window, min_periods, mean)) return false;
      value = mean;
      return true;
   }
   if(ParseWindowSuffix(column, "path_efficiency_", window))
   {
      double abs_path = 0.0;
      int min_periods = MathMax(2, window / 4);
      if(min_periods > window)
         min_periods = window;
      if(!SumAbsRet(rates, index, window, min_periods, abs_path)) return false;
      value = SafeDiv(MathAbs(RetAt(rates, index, window)), abs_path);
      return true;
   }
   if(ParseWindowSuffix(column, "close_to_sma_", window))
   {
      if(!MeanClose(rates, index, window, MinPeriodsForWindow(window, false), mean)) return false;
      value = SafeDiv(rates[index].close - mean, mean);
      return true;
   }
   if(ParseWindowSuffix(column, "tick_volume_z_", window))
   {
      return TickVolumeZ(rates, index, window, MinPeriodsForWindow(window, false), value);
   }
   if(ParseWindowSuffix(column, "close_z_", window))
   {
      if(!StdClose(rates, index, window, MinPeriodsForWindow(window, true), mean, std_value)) return false;
      value = SafeDiv(rates[index].close - mean, std_value);
      return true;
   }
   if(ParseWindowSuffix(column, "drawdown_from_roll_high_", window))
   {
      double high_value = 0.0;
      if(!MaxHigh(rates, index, window, MinPeriodsForWindow(window, true), high_value)) return false;
      value = SafeDiv(rates[index].close - high_value, rates[index].close);
      return true;
   }
   if(ParseWindowSuffix(column, "drawup_from_roll_low_", window))
   {
      double low_value = 0.0;
      if(!MinLow(rates, index, window, MinPeriodsForWindow(window, true), low_value)) return false;
      value = SafeDiv(rates[index].close - low_value, rates[index].close);
      return true;
   }
   if(ParseWindowSuffix(column, "volatility_", window))
   {
      if(!MeanStdRet(rates, index, window, MinPeriodsForWindow(window, true), mean, std_value)) return false;
      value = std_value;
      return true;
   }
   if(ParseWindowSuffix(column, "range_regime_", window))
   {
      if(!MeanRange(rates, index, window, MinPeriodsForWindow(window, true), mean)) return false;
      value = mean;
      return true;
   }
   if(column == "volatility_ratio_48_288")
   {
      double mean48 = 0.0, std48 = 0.0, mean288 = 0.0, std288 = 0.0;
      if(!MeanStdRet(rates, index, 48, MinPeriodsForWindow(48, true), mean48, std48)) return false;
      if(!MeanStdRet(rates, index, 288, MinPeriodsForWindow(288, true), mean288, std288)) return false;
      value = SafeDiv(std48, std288);
      return true;
   }
   if(column == "range_ratio_48_288")
   {
      double range48 = 0.0, range288 = 0.0;
      if(!MeanRange(rates, index, 48, MinPeriodsForWindow(48, true), range48)) return false;
      if(!MeanRange(rates, index, 288, MinPeriodsForWindow(288, true), range288)) return false;
      value = SafeDiv(range48, range288);
      return true;
   }
   if(column == "compression_range_12_vs_48")
   {
      double range12 = 0.0, range48 = 0.0;
      if(!MeanRange(rates, index, 12, MinPeriodsForWindow(12, false), range12)) return false;
      if(!MeanRange(rates, index, 48, MinPeriodsForWindow(48, false), range48)) return false;
      value = SafeDiv(range12, range48);
      return true;
   }
   if(column == "compression_range_6_vs_48")
   {
      double range6 = 0.0, range48 = 0.0;
      if(!MeanRange(rates, index, 6, 3, range6)) return false;
      if(!MeanRange(rates, index, 48, MinPeriodsForWindow(48, false), range48)) return false;
      value = SafeDiv(range6, range48);
      return true;
   }
   if(column == "compression_range_48_vs_144")
   {
      double range48 = 0.0, range144 = 0.0;
      if(!MeanRange(rates, index, 48, MinPeriodsForWindow(48, false), range48)) return false;
      if(!MeanRange(rates, index, 144, MinPeriodsForWindow(144, false), range144)) return false;
      value = SafeDiv(range48, range144);
      return true;
   }
   if(column == "compression_atr_12_vs_48")
   {
      double atr12 = 0.0, atr48 = 0.0;
      if(!MeanTrueRange(rates, index, 12, 6, atr12)) return false;
      if(!MeanTrueRange(rates, index, 48, 12, atr48)) return false;
      value = SafeDiv(atr12, atr48);
      return true;
   }
   if(column == "compression_atr_48_vs_144")
   {
      double atr48 = 0.0, atr144 = 0.0;
      if(!MeanTrueRange(rates, index, 48, 12, atr48)) return false;
      if(!MeanTrueRange(rates, index, 144, 36, atr144)) return false;
      value = SafeDiv(atr48, atr144);
      return true;
   }
   if(column == "volatility_range_12_vs_48")
   {
      double range12 = 0.0, range48 = 0.0;
      if(!MeanRange(rates, index, 12, 3, range12)) return false;
      if(!MeanRange(rates, index, 48, 12, range48)) return false;
      value = SafeDiv(range12, range48);
      return true;
   }
   if(column == "volatility_realized_12_vs_48")
   {
      double mean12 = 0.0, std12 = 0.0, mean48 = 0.0, std48 = 0.0;
      if(!MeanStdRet(rates, index, 12, 4, mean12, std12)) return false;
      if(!MeanStdRet(rates, index, 48, 12, mean48, std48)) return false;
      value = SafeDiv(std12, std48);
      return true;
   }
   if(column == "volatility_realized_48_vs_144")
   {
      double mean48 = 0.0, std48 = 0.0, mean144 = 0.0, std144 = 0.0;
      if(!MeanStdRet(rates, index, 48, 12, mean48, std48)) return false;
      if(!MeanStdRet(rates, index, 144, 36, mean144, std144)) return false;
      value = SafeDiv(std48, std144);
      return true;
   }
   if(column == "volume_z_48" || column == "liquidity_volume_z_48")
   {
      return TickVolumeZ(rates, index, 48, 12, value);
   }
   if(column == "volume_rank_144")
   {
      return TickVolumeRankPct(rates, index, 144, 36, value);
   }
   if(column == "liquidity_spread_pressure")
   {
      double spread_rank = 0.0, volume_rank = 0.0;
      if(!SpreadRankPct(rates, index, 144, 36, spread_rank)) return false;
      if(!TickVolumeRankPct(rates, index, 144, 36, volume_rank)) return false;
      value = spread_rank - volume_rank;
      return true;
   }
   if(column == "liquidity_decay_12")
   {
      double z = 0.0, z_mean = 0.0;
      if(!TickVolumeZ(rates, index, 48, 12, z)) return false;
      if(!MeanTickVolumeZ(rates, index, 12, 4, z_mean)) return false;
      value = z - z_mean;
      return true;
   }
   if(column == "position_close_in_48_range")
   {
      double high48 = 0.0, low48 = 0.0;
      if(!MaxHigh(rates, index, 48, 12, high48)) return false;
      if(!MinLow(rates, index, 48, 12, low48)) return false;
      value = SafeDiv(rates[index].close - low48, high48 - low48);
      return true;
   }
   if(column == "position_close_in_144_range")
   {
      double high144 = 0.0, low144 = 0.0;
      if(!MaxHigh(rates, index, 144, 36, high144)) return false;
      if(!MinLow(rates, index, 144, 36, low144)) return false;
      value = SafeDiv(rates[index].close - low144, high144 - low144);
      return true;
   }
   if(column == "reversal_pressure_12")
   {
      double high48 = 0.0, low48 = 0.0;
      if(!MaxHigh(rates, index, 48, 12, high48)) return false;
      if(!MinLow(rates, index, 48, 12, low48)) return false;
      const double position = SafeDiv(rates[index].close - low48, high48 - low48);
      const double pressure = MathAbs(position - 0.5);
      const double ret12 = RetAt(rates, index, 12);
      if(ret12 > 0.0) value = -pressure;
      else if(ret12 < 0.0) value = pressure;
      else value = 0.0;
      return true;
   }
   if(column == "breakout_up_48")
   {
      double high48_prev = 0.0, atr48 = 0.0;
      if(index <= 0) return false;
      if(!MaxHigh(rates, index - 1, 48, 12, high48_prev)) return false;
      if(!MeanTrueRange(rates, index, 48, 12, atr48)) return false;
      value = SafeDiv(rates[index].close - high48_prev, atr48);
      return true;
   }
   if(column == "breakout_down_48")
   {
      double low48_prev = 0.0, atr48 = 0.0;
      if(index <= 0) return false;
      if(!MinLow(rates, index - 1, 48, 12, low48_prev)) return false;
      if(!MeanTrueRange(rates, index, 48, 12, atr48)) return false;
      value = SafeDiv(low48_prev - rates[index].close, atr48);
      return true;
   }
   if(column == "breakout_up_144")
   {
      double high144_prev = 0.0, atr144 = 0.0;
      if(index <= 0) return false;
      if(!MaxHigh(rates, index - 1, 144, 36, high144_prev)) return false;
      if(!MeanTrueRange(rates, index, 144, 36, atr144)) return false;
      value = SafeDiv(rates[index].close - high144_prev, atr144);
      return true;
   }
   if(column == "breakout_down_144")
   {
      double low144_prev = 0.0, atr144 = 0.0;
      if(index <= 0) return false;
      if(!MinLow(rates, index - 1, 144, 36, low144_prev)) return false;
      if(!MeanTrueRange(rates, index, 144, 36, atr144)) return false;
      value = SafeDiv(low144_prev - rates[index].close, atr144);
      return true;
   }
   if(column == "drawdown_from_48_high")
   {
      double close48_max = 0.0;
      if(!MaxClose(rates, index, 48, 12, close48_max)) return false;
      value = SafeDiv(rates[index].close - close48_max, rates[index].close);
      return true;
   }
   if(column == "rebound_from_48_low")
   {
      double close48_min = 0.0;
      if(!MinClose(rates, index, 48, 12, close48_min)) return false;
      value = SafeDiv(rates[index].close - close48_min, rates[index].close);
      return true;
   }
   if(column == "drawdown_rebound_balance_48")
   {
      double close48_max = 0.0, close48_min = 0.0;
      if(!MaxClose(rates, index, 48, 12, close48_max)) return false;
      if(!MinClose(rates, index, 48, 12, close48_min)) return false;
      value = SafeDiv(rates[index].close - close48_min, rates[index].close)
            + SafeDiv(rates[index].close - close48_max, rates[index].close);
      return true;
   }
   if(column == "event_abs_ret_3_z_96" || column == "expansion_abs_ret_3_z_96")
   {
      if(!MeanStdAbsRet(rates, index, 96, 24, mean, std_value)) return false;
      value = SafeDiv(MathAbs(RetAt(rates, index, 3)) - mean, std_value);
      return true;
   }
   if(column == "event_range_z_96" || column == "expansion_range_z_96")
   {
      if(!MeanStdRange(rates, index, 96, 24, mean, std_value)) return false;
      value = SafeDiv(RangePctAt(rates, index) - mean, std_value);
      return true;
   }
   if(column == "expansion_release_12")
   {
      double range12 = 0.0, range48 = 0.0, range48_mean = 0.0, range48_std = 0.0;
      if(!MeanRange(rates, index, 12, 4, range12)) return false;
      if(!MeanRange(rates, index, 48, 12, range48)) return false;
      if(!MeanStdRange(rates, index, 48, 12, range48_mean, range48_std)) return false;
      value = SafeDiv(range12 - range48, range48_std);
      return true;
   }
   if(column == "trend_ratio_48_288")
   {
      value = SafeDiv(RetAt(rates, index, 48), MathAbs(RetAt(rates, index, 288)));
      return true;
   }
   if(StringFind(column, "rendered_") == 0)
   {
      value = RenderedClockFeature(column, rates[index].time + PeriodSeconds(PERIOD_M5));
      return true;
   }
   if(SessionTransitionFeature(column, rates[index].time + PeriodSeconds(PERIOD_M5), value))
      return true;
   if(LocalContextFeature(column, rates, index, value))
      return true;

   return false;
}

string DecisionFromScore(const double score)
{
   if(InpDecisionFamily == "diagnostic_rank_only" || !InpHasLowHigh)
      return "observe";
   if(InpDecisionFamily == "abstain_capable_long_short")
   {
      if(score >= InpScoreHigh) return "long";
      if(score <= InpScoreLow) return "short";
      return "flat";
   }
   if(InpDecisionFamily == "volatility_state_reversal_continuation_score_probe")
   {
      if(score >= InpScoreHigh) return "long";
      if(score <= InpScoreLow) return "short";
      return "flat";
   }
   if(InpDecisionFamily == "abstain_capable_direction_agnostic_tradeability")
      return (score >= InpScoreHigh ? "tradeable" : "flat");
   return "unknown";
}

bool IsManagedPosition(const ulong ticket)
{
   if(!PositionSelectByTicket(ticket))
      return false;
   if(PositionGetString(POSITION_SYMBOL) != _Symbol)
      return false;
   return ((ulong)PositionGetInteger(POSITION_MAGIC) == InpMagicNumber);
}

int ManagedPositionDirection()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsManagedPosition(ticket))
         continue;
      const long type = PositionGetInteger(POSITION_TYPE);
      if(type == POSITION_TYPE_BUY)
         return 1;
      if(type == POSITION_TYPE_SELL)
         return -1;
   }
   return 0;
}

bool CloseManagedPositions(const string reason, const datetime bar_time)
{
   bool ok = true;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      const ulong ticket = PositionGetTicket(i);
      if(ticket == 0 || !IsManagedPosition(ticket))
         continue;
      ResetLastError();
      if(!ExtTrade.PositionClose(ticket))
      {
         ok = false;
         WriteDiagnosticEvent("trade_close_failed", bar_time, StringFormat("ticket=%I64u reason=%s retcode=%u err=%d", ticket, reason, ExtTrade.ResultRetcode(), GetLastError()));
      }
      else
      {
         WriteDiagnosticEvent("trade_closed", bar_time, StringFormat("ticket=%I64u reason=%s", ticket, reason));
      }
   }
   if(ok)
      ExtBarsSinceEntry = 0;
   return ok;
}

bool OpenDecisionPosition(const string decision, const datetime bar_time)
{
   if(decision != "long" && decision != "short")
      return false;
   ResetLastError();
   bool ok = false;
   if(decision == "long")
      ok = ExtTrade.Buy(InpFixedLot, _Symbol);
   else
      ok = ExtTrade.Sell(InpFixedLot, _Symbol);
   if(!ok)
   {
      WriteDiagnosticEvent("trade_open_failed", bar_time, StringFormat("decision=%s lot=%.2f retcode=%u err=%d", decision, InpFixedLot, ExtTrade.ResultRetcode(), GetLastError()));
      return false;
   }
   ExtBarsSinceEntry = 0;
   WriteDiagnosticEvent("trade_opened", bar_time, StringFormat("decision=%s lot=%.2f", decision, InpFixedLot));
   return true;
}

void ExecuteDecision(const string decision, const datetime bar_time)
{
   if(!InpExecuteTrades)
      return;

   const int direction = ManagedPositionDirection();
   if(direction != 0)
      ExtBarsSinceEntry++;

   if(direction != 0 && InpHoldBars > 0 && ExtBarsSinceEntry >= InpHoldBars)
   {
      CloseManagedPositions("hold_bars_elapsed", bar_time);
      if(decision != "long" && decision != "short")
         return;
   }
   else if(direction == 1 && decision == "short")
   {
      CloseManagedPositions("opposite_short_signal", bar_time);
   }
   else if(direction == -1 && decision == "long")
   {
      CloseManagedPositions("opposite_long_signal", bar_time);
   }
   else if(direction != 0)
   {
      return;
   }

   if(ManagedPositionDirection() == 0)
      OpenDecisionPosition(decision, bar_time);
}

void WriteHeader()
{
   FileWrite(ExtOutputHandle,
             "bar_close_time",
             "symbol",
             "period",
             "input_family",
             "decision_family",
             "feature_count",
             "score",
             "decision",
             "spread_points",
             "tick_volume");
}

void WriteTelemetryRow(const datetime close_time, const double score, const string decision, const MqlRates &bar)
{
   FileWrite(ExtOutputHandle,
             TimeToString(close_time, TIME_DATE | TIME_SECONDS),
             _Symbol,
             EnumToString(_Period),
             InpInputFamily,
             InpDecisionFamily,
             InpFeatureCount,
             DoubleToString(score, 10),
             decision,
             (int)bar.spread,
             (long)bar.tick_volume);
}

bool BuildFeatureMatrix(matrixf &features, MqlRates &current_bar)
{
   MqlRates rates[];
   const int need = MathMax(InpHistoryBars, 600);
   const int copied = CopyRates(_Symbol, PERIOD_M5, 1, need, rates);
   if(copied <= 0)
   {
      ExtFeatureFailureCount++;
      WriteDiagnosticEvent("feature_matrix_failed", 0, StringFormat("CopyRates copied=%d need=%d", copied, need));
      return false;
   }
   const int index = copied - 1;
   if(copied < MathMin(need, InpHistoryBars))
   {
      ExtFeatureFailureCount++;
      WriteDiagnosticEvent("feature_matrix_failed", 0, StringFormat("insufficient_rates copied=%d need=%d history=%d", copied, need, InpHistoryBars));
      return false;
   }
   current_bar = rates[index];

   features.Init(1, InpFeatureCount);
   for(int i = 0; i < InpFeatureCount; i++)
   {
      double value = 0.0;
      if(!FeatureValue(ExtColumns[i], rates, index, value))
      {
         ExtFeatureFailureCount++;
         PrintFormat("SpaceSonar feature failed column=%s", ExtColumns[i]);
         WriteDiagnosticEvent("feature_value_failed", rates[index].time + PeriodSeconds(PERIOD_M5), ExtColumns[i]);
         return false;
      }
      if(!IsFinite(value))
         value = 0.0;
      features[0][i] = (float)value;
   }
   return true;
}

bool RunOneClosedBar()
{
   MqlRates current_bar;
   matrixf features;
   if(!BuildFeatureMatrix(features, current_bar))
      return false;

   vectorf score_vector(1);
   ResetLastError();
   if(!OnnxRun(ExtOnnxHandle, ONNX_NO_CONVERSION | ONNX_LOGLEVEL_INFO, features, score_vector))
   {
      ExtOnnxFailureCount++;
      PrintFormat("SpaceSonar L4 OnnxRun failed err=%d", GetLastError());
      WriteDiagnosticEvent("onnx_run_failed", current_bar.time + PeriodSeconds(PERIOD_M5), "OnnxRun returned false");
      return false;
   }

   const double score = (double)score_vector[0];
   const string decision = DecisionFromScore(score);
   const datetime close_time = current_bar.time + PeriodSeconds(PERIOD_M5);
   WriteTelemetryRow(close_time, score, decision, current_bar);
   ExecuteDecision(decision, close_time);
   FileFlush(ExtOutputHandle);
   ExtRowsWritten++;
   if(ShouldLogSample(ExtRowsWritten))
      WriteDiagnosticEvent("row_written", current_bar.time + PeriodSeconds(PERIOD_M5), decision);
   return true;
}

bool LoadFeatureColumns()
{
   string raw_columns = InpFeatureColumns;
   if(StringLen(InpFeatureColumnsPath) > 0)
   {
      const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
      ResetLastError();
      const int handle = FileOpen(InpFeatureColumnsPath, FILE_READ | FILE_TXT | FILE_ANSI | common_flag);
      if(handle == INVALID_HANDLE)
      {
         PrintFormat("Feature columns file open failed path=%s err=%d", InpFeatureColumnsPath, GetLastError());
         return false;
      }
      raw_columns = "";
      while(!FileIsEnding(handle))
         raw_columns += FileReadString(handle);
      FileClose(handle);
      StringReplace(raw_columns, "\r", "");
      StringReplace(raw_columns, "\n", "");
   }

   if(StringSplit(raw_columns, ';', ExtColumns) != InpFeatureCount)
   {
      PrintFormat("Feature column count mismatch expected=%d actual=%d", InpFeatureCount, ArraySize(ExtColumns));
      return false;
   }
   return true;
}

int OnInit()
{
   OpenDiagnosticLog();
   WriteDiagnosticEvent("init_start", 0, "score_probe_init");
   ExtTrade.SetExpertMagicNumber((long)InpMagicNumber);
   ExtTrade.SetDeviationInPoints(InpDeviationPoints);

   if(InpFeatureCount <= 0)
   {
      Print("InpFeatureCount must be positive.");
      WriteDiagnosticEvent("init_failed", 0, "feature_count_non_positive");
      return INIT_FAILED;
   }
   if(!LoadFeatureColumns())
   {
      WriteDiagnosticEvent("init_failed", 0, "feature_columns_load_failed");
      return INIT_FAILED;
   }
   WriteDiagnosticEvent("feature_columns_loaded", 0, StringFormat("count=%d", ArraySize(ExtColumns)));

   const uint onnx_flags = (uint)((InpUseCommonFiles ? ONNX_COMMON_FOLDER : 0) | ONNX_LOGLEVEL_INFO | ONNX_USE_CPU_ONLY);
   ResetLastError();
   ExtOnnxHandle = OnnxCreate(InpOnnxPath, onnx_flags);
   if(ExtOnnxHandle == INVALID_HANDLE || ExtOnnxHandle == 0)
   {
      PrintFormat("SpaceSonar L4 OnnxCreate failed path=%s err=%d", InpOnnxPath, GetLastError());
      ExtOnnxFailureCount++;
      WriteDiagnosticEvent("onnx_create_failed", 0, InpOnnxPath);
      return INIT_FAILED;
   }
   WriteDiagnosticEvent("onnx_created", 0, InpOnnxPath);

   ulong input_shape[2];
   input_shape[0] = 1;
   input_shape[1] = (ulong)InpFeatureCount;
   ulong output_shape[1];
   output_shape[0] = 1;
   if(!OnnxSetInputShape(ExtOnnxHandle, 0, input_shape))
   {
      PrintFormat("SpaceSonar L4 OnnxSetInputShape failed err=%d", GetLastError());
      WriteDiagnosticEvent("onnx_input_shape_failed", 0, StringFormat("feature_count=%d", InpFeatureCount));
      return INIT_FAILED;
   }
   if(!OnnxSetOutputShape(ExtOnnxHandle, 0, output_shape))
   {
      PrintFormat("SpaceSonar L4 OnnxSetOutputShape failed err=%d", GetLastError());
      WriteDiagnosticEvent("onnx_output_shape_failed", 0, "output_shape=1");
      return INIT_FAILED;
   }
   WriteDiagnosticEvent("onnx_shapes_set", 0, StringFormat("feature_count=%d", InpFeatureCount));

   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   ExtOutputHandle = FileOpen(InpOutputPath, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(ExtOutputHandle == INVALID_HANDLE)
   {
      PrintFormat("SpaceSonar L4 output open failed path=%s err=%d", InpOutputPath, GetLastError());
      WriteDiagnosticEvent("output_open_failed", 0, InpOutputPath);
      return INIT_FAILED;
   }
   WriteHeader();
   FileFlush(ExtOutputHandle);
   WriteDiagnosticEvent("init_succeeded", 0, "output_header_written");
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   WriteDiagnosticEvent("deinit_start", 0, StringFormat("reason=%d", reason));
   if(ExtOutputHandle != INVALID_HANDLE)
   {
      FileClose(ExtOutputHandle);
      ExtOutputHandle = INVALID_HANDLE;
   }
   if(ExtOnnxHandle != INVALID_HANDLE && ExtOnnxHandle != 0)
   {
      ResetLastError();
      const bool released = OnnxRelease(ExtOnnxHandle);
      PrintFormat("SpaceSonar L4 ONNX release released=%s last_error=%d rows=%d",
                  (released ? "true" : "false"), GetLastError(), ExtRowsWritten);
      WriteDiagnosticEvent("onnx_released", 0, StringFormat("released=%s", (released ? "true" : "false")));
      ExtOnnxHandle = INVALID_HANDLE;
   }
   WriteDiagnosticEvent("deinit_complete", 0, "score_probe_deinit");
   if(ExtDiagnosticHandle != INVALID_HANDLE)
   {
      FileClose(ExtDiagnosticHandle);
      ExtDiagnosticHandle = INVALID_HANDLE;
   }
}

void OnTick()
{
   ExtTicksSeen++;
   if(ExtTicksSeen <= 5 || (ExtTicksSeen % 10000) == 0)
      WriteDiagnosticEvent("tick_seen", 0, "");

   if(InpMaxRows > 0 && ExtRowsWritten >= InpMaxRows)
   {
      if(!ExtMaxRowsReachedLogged)
      {
         WriteDiagnosticEvent("max_rows_reached", 0, StringFormat("InpMaxRows=%d", InpMaxRows));
         ExtMaxRowsReachedLogged = true;
      }
      return;
   }

   const datetime closed_time = iTime(_Symbol, PERIOD_M5, 1);
   if(closed_time <= 0)
   {
      if(ExtTicksSeen <= 5)
         WriteDiagnosticEvent("closed_time_missing", 0, "iTime shift=1 returned <=0");
      return;
   }
   if(closed_time == ExtLastClosedBarTime)
      return;

   ExtClosedBarCandidates++;
   if(ShouldLogSample(ExtClosedBarCandidates))
      WriteDiagnosticEvent("closed_bar_candidate", closed_time, "");
   ExtLastClosedBarTime = closed_time;
   if(!RunOneClosedBar())
      WriteDiagnosticEvent("closed_bar_no_row", closed_time, "RunOneClosedBar returned false");
}
