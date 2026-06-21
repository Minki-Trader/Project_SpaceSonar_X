//+------------------------------------------------------------------+
//| SpaceSonar US100 M5 History Audit                                |
//| Non-trading EA: pulls broker MT5 bars and writes coverage reports |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Non-trading broker-history audit for US100 M5 coverage, gaps, spread, and volume."

input string          InpSymbol              = "US100";
input ENUM_TIMEFRAMES InpTimeframe           = PERIOD_M5;
input datetime        InpFrom                = D'1970.01.01 00:00';
input datetime        InpTo                  = 0;
input int             InpExpectedFullDayBars = 276;
input int             InpRetryCount          = 8;
input int             InpRetrySleepMs        = 1500;
input bool            InpUseCommonFiles      = true;
input bool            InpRemoveAfterRun      = true;

struct DayStats
{
   string   date_key;
   datetime first_time;
   datetime last_time;
   int      bar_count;
   int      duplicate_count;
   int      internal_gap_count;
   int      max_gap_seconds;
   datetime first_gap_from;
   datetime first_gap_to;
   long     tick_volume_sum;
   long     real_volume_sum;
   int      zero_tick_volume_count;
   int      zero_real_volume_count;
   int      spread_min;
   int      spread_max;
   long     spread_sum;
   int      spread_zero_count;
};

string DateKey(const datetime value)
{
   MqlDateTime parts;
   TimeToStruct(value, parts);
   return StringFormat("%04d.%02d.%02d", parts.year, parts.mon, parts.day);
}

string HhMm(const datetime value)
{
   MqlDateTime parts;
   TimeToStruct(value, parts);
   return StringFormat("%02d:%02d", parts.hour, parts.min);
}

string CompactTimestamp(const datetime value)
{
   MqlDateTime parts;
   TimeToStruct(value, parts);
   return StringFormat("%04d%02d%02d_%02d%02d%02d",
                       parts.year, parts.mon, parts.day,
                       parts.hour, parts.min, parts.sec);
}

string TimeText(const datetime value)
{
   return TimeToString(value, TIME_DATE | TIME_SECONDS);
}

string OptionalTimeText(const datetime value)
{
   if(value <= 0)
      return "";
   return TimeText(value);
}

void ResetDay(DayStats &day, const string date_key)
{
   day.date_key = date_key;
   day.first_time = 0;
   day.last_time = 0;
   day.bar_count = 0;
   day.duplicate_count = 0;
   day.internal_gap_count = 0;
   day.max_gap_seconds = 0;
   day.first_gap_from = 0;
   day.first_gap_to = 0;
   day.tick_volume_sum = 0;
   day.real_volume_sum = 0;
   day.zero_tick_volume_count = 0;
   day.zero_real_volume_count = 0;
   day.spread_min = INT_MAX;
   day.spread_max = INT_MIN;
   day.spread_sum = 0;
   day.spread_zero_count = 0;
}

bool EnsureFolder(const string path, const int common_flag)
{
   ResetLastError();
   if(FolderCreate(path, common_flag))
      return true;

   const int err = GetLastError();
   if(err == 5016) // ERR_FILE_ALREADY_EXISTS
      return true;

   PrintFormat("FolderCreate failed: %s err=%d", path, err);
   return false;
}

bool EnsureOutputFolders(const string run_dir, const bool use_common_files)
{
   const int common_flag = (use_common_files ? FILE_COMMON : 0);
   if(!EnsureFolder("SpaceSonar", common_flag))
      return false;
   if(!EnsureFolder("SpaceSonar\\history_audit", common_flag))
      return false;
   if(!EnsureFolder(run_dir, common_flag))
      return false;
   return true;
}

void AddBarToDay(DayStats &day, const MqlRates &bar)
{
   if(day.bar_count == 0)
      day.first_time = bar.time;
   day.last_time = bar.time;
   day.bar_count++;

   day.tick_volume_sum += (long)bar.tick_volume;
   day.real_volume_sum += (long)bar.real_volume;

   if(bar.tick_volume <= 0)
      day.zero_tick_volume_count++;
   if(bar.real_volume <= 0)
      day.zero_real_volume_count++;

   const int spread = (int)bar.spread;
   if(spread < day.spread_min)
      day.spread_min = spread;
   if(spread > day.spread_max)
      day.spread_max = spread;
   day.spread_sum += spread;
   if(spread <= 0)
      day.spread_zero_count++;
}

string SessionStatus(const DayStats &day,
                     const bool is_first_day,
                     const bool is_last_day,
                     const int expected_full_day_bars)
{
   if(day.duplicate_count > 0 || day.bar_count > expected_full_day_bars)
      return "over_expected_or_duplicate_candidate";

   if(day.internal_gap_count > 0)
      return "gap_or_missing_candidate";

   if(day.bar_count == expected_full_day_bars)
      return "normal_full_day_candidate";

   if(is_first_day || is_last_day)
      return "range_edge_partial";

   if(day.bar_count > 0 && day.bar_count < expected_full_day_bars)
      return "early_close_candidate";

   return "unknown";
}

void WriteDailyRow(const int daily_handle,
                   const DayStats &day,
                   const bool is_first_day,
                   const bool is_last_day,
                   const int expected_full_day_bars)
{
   const double avg_spread = (day.bar_count > 0 ? (double)day.spread_sum / (double)day.bar_count : 0.0);
   const int spread_min = (day.spread_min == INT_MAX ? 0 : day.spread_min);
   const int spread_max = (day.spread_max == INT_MIN ? 0 : day.spread_max);
   const string status = SessionStatus(day, is_first_day, is_last_day, expected_full_day_bars);

   FileWrite(daily_handle,
             day.date_key,
             day.bar_count,
             expected_full_day_bars,
             status,
             (is_first_day ? 1 : 0),
             (is_last_day ? 1 : 0),
             TimeText(day.first_time),
             TimeText(day.last_time),
             HhMm(day.first_time),
             HhMm(day.last_time),
             day.internal_gap_count,
             day.max_gap_seconds,
             OptionalTimeText(day.first_gap_from),
             OptionalTimeText(day.first_gap_to),
             day.duplicate_count,
             spread_min,
             spread_max,
             StringFormat("%.2f", avg_spread),
             day.spread_zero_count,
             day.tick_volume_sum,
             day.real_volume_sum,
             day.zero_tick_volume_count,
             day.zero_real_volume_count);
}

void WriteSummary(const string summary_path,
                  const string daily_path,
                  const string gaps_path,
                  const string symbol,
                  const ENUM_TIMEFRAMES timeframe,
                  const datetime from_time,
                  const datetime to_time,
                  const int copied,
                  const datetime first_bar,
                  const datetime last_bar,
                  const int day_count,
                  const int normal_days,
                  const int early_close_candidates,
                  const int gap_days,
                  const int duplicate_days,
                  const int range_edge_days,
                  const int total_gap_events,
                  const int max_gap_seconds,
                  const bool use_common_files)
{
   const int common_flag = (use_common_files ? FILE_COMMON : 0);
   const int handle = FileOpen(summary_path, FILE_WRITE | FILE_TXT | FILE_ANSI | common_flag);
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("Failed to write summary: %s err=%d", summary_path, GetLastError());
      return;
   }

   FileWriteString(handle, "SpaceSonar US100 M5 History Audit\n");
   FileWriteString(handle, "claim_boundary: broker MT5 history observation only; not runtime authority, economics pass, or live-readiness claim.\n");
   FileWriteString(handle, StringFormat("generated_at_local: %s\n", TimeText(TimeLocal())));
   FileWriteString(handle, StringFormat("file_scope: %s\n", (use_common_files ? "common_files" : "terminal_or_tester_files")));
   FileWriteString(handle, StringFormat("terminal_data_path: %s\n", TerminalInfoString(TERMINAL_DATA_PATH)));
   FileWriteString(handle, StringFormat("common_data_path: %s\n", TerminalInfoString(TERMINAL_COMMONDATA_PATH)));
   FileWriteString(handle, StringFormat("symbol: %s\n", symbol));
   FileWriteString(handle, StringFormat("timeframe: %s\n", EnumToString(timeframe)));
   FileWriteString(handle, StringFormat("requested_from_mt5: %s\n", TimeText(from_time)));
   FileWriteString(handle, StringFormat("requested_to_mt5: %s\n", TimeText(to_time)));
   FileWriteString(handle, StringFormat("copied_bars: %d\n", copied));
   FileWriteString(handle, StringFormat("first_bar_mt5: %s\n", TimeText(first_bar)));
   FileWriteString(handle, StringFormat("last_bar_mt5: %s\n", TimeText(last_bar)));
   FileWriteString(handle, StringFormat("daily_rows: %d\n", day_count));
   FileWriteString(handle, StringFormat("normal_full_day_candidates: %d\n", normal_days));
   FileWriteString(handle, StringFormat("early_close_candidates: %d\n", early_close_candidates));
   FileWriteString(handle, StringFormat("gap_or_missing_days: %d\n", gap_days));
   FileWriteString(handle, StringFormat("duplicate_or_over_expected_days: %d\n", duplicate_days));
   FileWriteString(handle, StringFormat("range_edge_partial_days: %d\n", range_edge_days));
   FileWriteString(handle, StringFormat("total_internal_gap_events: %d\n", total_gap_events));
   FileWriteString(handle, StringFormat("max_gap_seconds: %d\n", max_gap_seconds));
   FileWriteString(handle, StringFormat("daily_csv: %s\n", daily_path));
   FileWriteString(handle, StringFormat("gaps_csv: %s\n", gaps_path));
   FileWriteString(handle, "time_axis_note: MQL5 datetime values are written as MT5 terminal/server bar-open timestamps; UTC conversion is intentionally not claimed here.\n");
   FileWriteString(handle, "download_note: CopyRates/Bars calls request the terminal to load available broker history; terminal max-bars and broker availability still cap the result.\n");
   FileClose(handle);
}

int LoadRatesWithRetries(const string symbol,
                         const ENUM_TIMEFRAMES timeframe,
                         const datetime from_time,
                         const datetime to_time,
                         MqlRates &rates[])
{
   int copied = -1;
   for(int attempt = 1; attempt <= MathMax(1, InpRetryCount); attempt++)
   {
      ResetLastError();
      const int bars_count = Bars(symbol, timeframe, from_time, to_time);
      const int bars_err = GetLastError();

      ResetLastError();
      copied = CopyRates(symbol, timeframe, from_time, to_time, rates);
      const int copy_err = GetLastError();

      PrintFormat("History load attempt %d/%d: Bars=%d err=%d CopyRates=%d err=%d",
                  attempt, MathMax(1, InpRetryCount), bars_count, bars_err, copied, copy_err);

      if(copied > 0)
         return copied;

      Sleep(MathMax(0, InpRetrySleepMs));
   }
   return copied;
}

bool g_audit_done = false;

bool RunAudit(const string trigger)
{
   PrintFormat("SpaceSonar history audit trigger: %s", trigger);

   const string symbol = InpSymbol;
   if(symbol == "")
   {
      Print("InpSymbol is empty.");
      return false;
   }

   if(!SymbolSelect(symbol, true))
   {
      PrintFormat("SymbolSelect failed: %s err=%d", symbol, GetLastError());
      return false;
   }

   const int timeframe_seconds = PeriodSeconds(InpTimeframe);
   if(timeframe_seconds <= 0)
   {
      PrintFormat("Unsupported timeframe: %s", EnumToString(InpTimeframe));
      return false;
   }

   datetime to_time = InpTo;
   if(to_time <= 0)
      to_time = TimeCurrent();
   if(to_time <= 0)
      to_time = TimeTradeServer();
   if(to_time <= 0)
      to_time = TimeLocal();

   const datetime from_time = InpFrom;
   if(from_time >= to_time)
   {
      PrintFormat("Invalid requested range: from=%s to=%s", TimeText(from_time), TimeText(to_time));
      return false;
   }

   MqlRates rates[];
   ArraySetAsSeries(rates, false);
   const int copied = LoadRatesWithRetries(symbol, InpTimeframe, from_time, to_time, rates);
   if(copied <= 0)
   {
      PrintFormat("No bars copied for %s %s from %s to %s. LastError=%d",
                  symbol, EnumToString(InpTimeframe), TimeText(from_time), TimeText(to_time), GetLastError());
      return false;
   }

   const datetime first_bar_time = rates[0].time;
   const datetime last_bar_time = rates[copied - 1].time;
   const string first_day_key = DateKey(first_bar_time);
   const string last_day_key = DateKey(last_bar_time);

   const string run_id = "run_" + CompactTimestamp(TimeLocal()) + "_" + IntegerToString((int)(GetTickCount64() % 1000000)) + "_" + symbol + "_" + EnumToString(InpTimeframe);
   const string run_dir = "SpaceSonar\\history_audit\\" + run_id;
   if(!EnsureOutputFolders(run_dir, InpUseCommonFiles))
      return false;

   const string daily_path = run_dir + "\\daily.csv";
   const string gaps_path = run_dir + "\\gaps.csv";
   const string summary_path = run_dir + "\\summary.txt";

   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   const int daily_handle = FileOpen(daily_path, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(daily_handle == INVALID_HANDLE)
   {
      PrintFormat("Failed to open daily csv: %s err=%d", daily_path, GetLastError());
      return false;
   }

   const int gaps_handle = FileOpen(gaps_path, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(gaps_handle == INVALID_HANDLE)
   {
      FileClose(daily_handle);
      PrintFormat("Failed to open gaps csv: %s err=%d", gaps_path, GetLastError());
      return false;
   }

   FileWrite(daily_handle,
             "mt5_date",
             "bar_count",
             "expected_full_day_bars",
             "session_status",
             "is_first_copied_day",
             "is_last_copied_day",
             "first_bar_mt5",
             "last_bar_mt5",
             "first_hhmm_mt5",
             "last_hhmm_mt5",
             "internal_gap_count",
             "max_gap_seconds",
             "first_gap_from_mt5",
             "first_gap_to_mt5",
             "duplicate_count",
             "spread_min_points",
             "spread_max_points",
             "spread_avg_points",
             "spread_zero_count",
             "tick_volume_sum",
             "real_volume_sum",
             "zero_tick_volume_count",
             "zero_real_volume_count");

   FileWrite(gaps_handle,
             "mt5_date",
             "prev_bar_mt5",
             "next_bar_mt5",
             "gap_seconds",
             "missing_m5_bar_estimate");

   DayStats day;
   ResetDay(day, DateKey(rates[0].time));

   int day_count = 0;
   int normal_days = 0;
   int early_close_candidates = 0;
   int gap_days = 0;
   int duplicate_days = 0;
   int range_edge_days = 0;
   int total_gap_events = 0;
   int global_max_gap_seconds = 0;

   datetime previous_time = 0;

   for(int i = 0; i < copied; i++)
   {
      const MqlRates bar = rates[i];
      const string bar_day_key = DateKey(bar.time);

      if(day.bar_count > 0 && bar_day_key != day.date_key)
      {
         const bool is_first_day = (day.date_key == first_day_key);
         const bool is_last_day = (day.date_key == last_day_key);
         const string status = SessionStatus(day, is_first_day, is_last_day, InpExpectedFullDayBars);
         if(status == "normal_full_day_candidate")
            normal_days++;
         else if(status == "early_close_candidate")
            early_close_candidates++;
         else if(status == "gap_or_missing_candidate")
            gap_days++;
         else if(status == "over_expected_or_duplicate_candidate")
            duplicate_days++;
         else if(status == "range_edge_partial")
            range_edge_days++;

         WriteDailyRow(daily_handle, day, is_first_day, is_last_day, InpExpectedFullDayBars);
         day_count++;
         ResetDay(day, bar_day_key);
      }

      if(previous_time > 0)
      {
         const int delta_seconds = (int)(bar.time - previous_time);
         if(delta_seconds == 0)
         {
            day.duplicate_count++;
         }
         else if(delta_seconds > timeframe_seconds && DateKey(previous_time) == bar_day_key)
         {
            day.internal_gap_count++;
            total_gap_events++;
            if(delta_seconds > day.max_gap_seconds)
               day.max_gap_seconds = delta_seconds;
            if(delta_seconds > global_max_gap_seconds)
               global_max_gap_seconds = delta_seconds;
            if(day.first_gap_from <= 0)
            {
               day.first_gap_from = previous_time;
               day.first_gap_to = bar.time;
            }

            const int missing_estimate = (delta_seconds / timeframe_seconds) - 1;
            FileWrite(gaps_handle,
                      bar_day_key,
                      TimeText(previous_time),
                      TimeText(bar.time),
                      delta_seconds,
                      missing_estimate);
         }
      }

      AddBarToDay(day, bar);
      previous_time = bar.time;
   }

   if(day.bar_count > 0)
   {
      const bool is_first_day = (day.date_key == first_day_key);
      const bool is_last_day = (day.date_key == last_day_key);
      const string status = SessionStatus(day, is_first_day, is_last_day, InpExpectedFullDayBars);
      if(status == "normal_full_day_candidate")
         normal_days++;
      else if(status == "early_close_candidate")
         early_close_candidates++;
      else if(status == "gap_or_missing_candidate")
         gap_days++;
      else if(status == "over_expected_or_duplicate_candidate")
         duplicate_days++;
      else if(status == "range_edge_partial")
         range_edge_days++;

      WriteDailyRow(daily_handle, day, is_first_day, is_last_day, InpExpectedFullDayBars);
      day_count++;
   }

   FileClose(daily_handle);
   FileClose(gaps_handle);

   WriteSummary(summary_path,
                daily_path,
                gaps_path,
                symbol,
                InpTimeframe,
                from_time,
                to_time,
                copied,
                first_bar_time,
                last_bar_time,
                day_count,
                normal_days,
                early_close_candidates,
                gap_days,
                duplicate_days,
                range_edge_days,
                total_gap_events,
                global_max_gap_seconds,
                InpUseCommonFiles);

   PrintFormat("SpaceSonar history audit complete. Files: %s, %s, %s",
               daily_path, gaps_path, summary_path);
   if(InpUseCommonFiles)
      PrintFormat("Common files base: %s\\Files", TerminalInfoString(TERMINAL_COMMONDATA_PATH));
   else
      PrintFormat("Terminal/tester files base: %s\\MQL5\\Files", TerminalInfoString(TERMINAL_DATA_PATH));

   g_audit_done = true;
   return true;
}

int OnInit()
{
   if(MQLInfoInteger(MQL_TESTER))
   {
      Print("SpaceSonar history audit deferred until tester OnDeinit so full generated history is visible.");
      return INIT_SUCCEEDED;
   }

   if(!RunAudit("chart_oninit"))
      return INIT_FAILED;

   if(InpRemoveAfterRun)
      ExpertRemove();

   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(MQLInfoInteger(MQL_TESTER) && !g_audit_done)
   {
      if(!RunAudit("tester_ondeinit"))
         PrintFormat("SpaceSonar history audit failed during tester OnDeinit. deinit_reason=%d", reason);
   }
}
