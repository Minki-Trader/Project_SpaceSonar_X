//+------------------------------------------------------------------+
//| SpaceSonar L4 Score Replay Decision Probe                        |
//| Replays MT5 score telemetry into sparse tester trades.            |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Score-telemetry replay EA for sparse decision-execution probing."

#include <Trade/Trade.mqh>

input string InpScoreTelemetryPath      = "SpaceSonar\\l4_score_probe\\attempt\\score_telemetry.csv";
input string InpExecutionTelemetryPath  = "SpaceSonar\\l4_decision_replay\\attempt\\execution_telemetry.csv";
input bool   InpUseCommonFiles          = true;
input string InpDecisionFamily          = "";
input string InpDirectionPolicy         = "momentum_ret_1";
input double InpScoreHigh               = 0.0;
input double InpFixedLot                = 0.02;
input int    InpHoldBars                = 1;
input bool   InpCloseOnFlat             = true;
input int    InpMaxSpreadPoints         = 0;
input int    InpDeviationPoints         = 20;
input int    InpMagicNumber             = 260621;

CTrade  ExtTrade;
int     ExtExecutionHandle = INVALID_HANDLE;
datetime ExtLastClosedBarTime = 0;
datetime ExtEntryCloseTime = 0;
int     ExtRowsLoaded = 0;
int     ExtRowsObserved = 0;
int     ExtOrdersAttempted = 0;
datetime ExtTelemetryTimes[];
double  ExtTelemetryScores[];
string  ExtTelemetryDecisions[];

bool IsFinite(const double value)
{
   return MathIsValidNumber(value);
}

void AppendTelemetryRow(const datetime close_time, const double score, const string decision)
{
   const int size = ArraySize(ExtTelemetryTimes);
   ArrayResize(ExtTelemetryTimes, size + 1);
   ArrayResize(ExtTelemetryScores, size + 1);
   ArrayResize(ExtTelemetryDecisions, size + 1);
   ExtTelemetryTimes[size] = close_time;
   ExtTelemetryScores[size] = score;
   ExtTelemetryDecisions[size] = decision;
   ExtRowsLoaded++;
}

bool LoadScoreTelemetry()
{
   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   const int handle = FileOpen(InpScoreTelemetryPath, FILE_READ | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("Score replay telemetry open failed path=%s err=%d", InpScoreTelemetryPath, GetLastError());
      return false;
   }

   for(int i = 0; i < 10 && !FileIsEnding(handle); i++)
      FileReadString(handle);

   while(!FileIsEnding(handle))
   {
      const string time_text = FileReadString(handle);
      if(StringLen(time_text) == 0)
         break;
      const string symbol_text = FileReadString(handle);
      const string period_text = FileReadString(handle);
      const string input_family = FileReadString(handle);
      const string decision_family = FileReadString(handle);
      const string feature_count = FileReadString(handle);
      const string score_text = FileReadString(handle);
      const string decision_text = FileReadString(handle);
      const string spread_points = FileReadString(handle);
      const string tick_volume = FileReadString(handle);

      const datetime close_time = StringToTime(time_text);
      const double score = StringToDouble(score_text);
      if(close_time > 0 && IsFinite(score))
         AppendTelemetryRow(close_time, score, decision_text);
   }
   FileClose(handle);
   return ExtRowsLoaded > 0;
}

int FindTelemetryIndex(const datetime close_time)
{
   const int total = ArraySize(ExtTelemetryTimes);
   for(int i = 0; i < total; i++)
   {
      if(ExtTelemetryTimes[i] == close_time)
         return i;
      if(ExtTelemetryTimes[i] > close_time)
         return -1;
   }
   return -1;
}

double Ret1()
{
   const double close1 = iClose(_Symbol, PERIOD_M5, 1);
   const double close2 = iClose(_Symbol, PERIOD_M5, 2);
   if(close2 == 0.0 || !IsFinite(close1) || !IsFinite(close2))
      return 0.0;
   return (close1 - close2) / close2;
}

string DirectionFromPolicy()
{
   const double ret1 = Ret1();
   if(InpDirectionPolicy == "long_only")
      return "long";
   if(InpDirectionPolicy == "short_only")
      return "short";
   if(InpDirectionPolicy == "momentum_ret_1")
      return (ret1 >= 0.0 ? "long" : "short");
   if(InpDirectionPolicy == "contrarian_ret_1")
      return (ret1 >= 0.0 ? "short" : "long");
   return "flat";
}

string ExecutionSignal(const string source_decision, const double score)
{
   const string decision = source_decision;
   if(InpDecisionFamily == "diagnostic_rank_only")
      return "flat";
   if(InpDecisionFamily == "abstain_capable_long_short")
   {
      if(decision == "long" || decision == "short")
         return decision;
      return "flat";
   }
   if(InpDecisionFamily == "abstain_capable_direction_agnostic_tradeability")
   {
      if(decision != "tradeable" && decision != "long" && decision != "short")
         return "flat";
      if(score < InpScoreHigh)
         return "flat";
      return DirectionFromPolicy();
   }
   return "flat";
}

bool HasOurPosition(ENUM_POSITION_TYPE &position_type)
{
   if(!PositionSelect(_Symbol))
      return false;
   const long magic = (long)PositionGetInteger(POSITION_MAGIC);
   if(magic != (long)InpMagicNumber)
      return false;
   position_type = (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE);
   return true;
}

bool CloseOurPosition()
{
   ENUM_POSITION_TYPE position_type;
   if(!HasOurPosition(position_type))
      return true;
   ResetLastError();
   const bool closed = ExtTrade.PositionClose(_Symbol);
   if(!closed)
      PrintFormat("Score replay close failed err=%d", GetLastError());
   if(closed)
      ExtEntryCloseTime = 0;
   return closed;
}

string ApplySignal(const datetime close_time, const string signal)
{
   ENUM_POSITION_TYPE position_type;
   const bool has_position = HasOurPosition(position_type);
   if(has_position && ExtEntryCloseTime > 0 && InpHoldBars > 0)
   {
      const int elapsed = (int)((close_time - ExtEntryCloseTime) / PeriodSeconds(PERIOD_M5));
      if(elapsed >= InpHoldBars)
      {
         CloseOurPosition();
         return "close_hold_elapsed";
      }
   }

   if(signal == "flat")
   {
      if(InpCloseOnFlat && has_position)
      {
         CloseOurPosition();
         return "close_flat";
      }
      return "no_trade_flat";
   }

   if(InpMaxSpreadPoints > 0)
   {
      const long spread = SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
      if(spread > InpMaxSpreadPoints)
         return "skip_spread";
   }

   if(has_position)
   {
      if((signal == "long" && position_type == POSITION_TYPE_BUY) ||
         (signal == "short" && position_type == POSITION_TYPE_SELL))
         return "hold_same_direction";
      CloseOurPosition();
   }

   ResetLastError();
   bool opened = false;
   if(signal == "long")
      opened = ExtTrade.Buy(InpFixedLot, _Symbol, 0.0, 0.0, 0.0, "SpaceSonar score replay");
   else if(signal == "short")
      opened = ExtTrade.Sell(InpFixedLot, _Symbol, 0.0, 0.0, 0.0, "SpaceSonar score replay");

   ExtOrdersAttempted++;
   if(!opened)
   {
      PrintFormat("Score replay open failed signal=%s err=%d", signal, GetLastError());
      return "open_failed";
   }
   ExtEntryCloseTime = close_time;
   return (signal == "long" ? "open_long" : "open_short");
}

void WriteExecutionHeader()
{
   FileWrite(ExtExecutionHandle,
             "bar_close_time",
             "symbol",
             "period",
             "decision_family",
             "direction_policy",
             "score",
             "source_decision",
             "execution_signal",
             "action",
             "spread_points");
}

void WriteExecutionRow(
   const datetime close_time,
   const double score,
   const string source_decision,
   const string signal,
   const string action
)
{
   FileWrite(ExtExecutionHandle,
             TimeToString(close_time, TIME_DATE | TIME_SECONDS),
             _Symbol,
             EnumToString(_Period),
             InpDecisionFamily,
             InpDirectionPolicy,
             DoubleToString(score, 10),
             source_decision,
             signal,
             action,
             (int)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD));
}

int OnInit()
{
   ExtTrade.SetExpertMagicNumber(InpMagicNumber);
   ExtTrade.SetDeviationInPoints(InpDeviationPoints);

   if(!LoadScoreTelemetry())
      return INIT_FAILED;

   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   ExtExecutionHandle = FileOpen(InpExecutionTelemetryPath, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(ExtExecutionHandle == INVALID_HANDLE)
   {
      PrintFormat("Score replay output open failed path=%s err=%d", InpExecutionTelemetryPath, GetLastError());
      return INIT_FAILED;
   }
   WriteExecutionHeader();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   if(ExtExecutionHandle != INVALID_HANDLE)
   {
      FileClose(ExtExecutionHandle);
      ExtExecutionHandle = INVALID_HANDLE;
   }
   PrintFormat("SpaceSonar score replay deinit reason=%d rows_loaded=%d rows_observed=%d orders_attempted=%d",
               reason, ExtRowsLoaded, ExtRowsObserved, ExtOrdersAttempted);
}

void OnTick()
{
   const datetime closed_open_time = iTime(_Symbol, PERIOD_M5, 1);
   if(closed_open_time <= 0 || closed_open_time == ExtLastClosedBarTime)
      return;
   ExtLastClosedBarTime = closed_open_time;

   const datetime close_time = closed_open_time + PeriodSeconds(PERIOD_M5);
   const int index = FindTelemetryIndex(close_time);
   if(index < 0)
      return;

   const double score = ExtTelemetryScores[index];
   const string source_decision = ExtTelemetryDecisions[index];
   const string signal = ExecutionSignal(source_decision, score);
   const string action = ApplySignal(close_time, signal);
   WriteExecutionRow(close_time, score, source_decision, signal, action);
   ExtRowsObserved++;
}
