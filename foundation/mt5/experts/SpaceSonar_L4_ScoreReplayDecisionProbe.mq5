//+------------------------------------------------------------------+
//| SpaceSonar L4 Score Replay Decision Probe                        |
//| Replays MT5 score telemetry into sparse tester trades.            |
//+------------------------------------------------------------------+
#property strict
#property version   "1.03"
#property description "Score-telemetry replay EA for sparse decision-execution probing."

#include <Trade/Trade.mqh>
#include "..\include\SpaceSonar_TradeShapeKpi.mqh"

input string InpScoreTelemetryPath      = "SpaceSonar\\l4_score_probe\\attempt\\score_telemetry.csv";
input string InpExecutionTelemetryPath  = "SpaceSonar\\l4_decision_replay\\attempt\\execution_telemetry.csv";
input string InpTradeShapeTelemetryPath = "SpaceSonar\\l4_decision_replay\\attempt\\trade_shape_telemetry.csv";
input string InpAttemptId               = "";
input bool   InpEmitTradeShapeTelemetry = true;
input bool   InpUseCommonFiles          = true;
input string InpDecisionFamily          = "";
input string InpDirectionPolicy         = "momentum_ret_1";
input double InpScoreHigh               = 0.0;
input double InpScoreLow                = 0.0;
input double InpFixedLot                = 0.02;
input int    InpHoldBars                = 1;
input bool   InpCloseOnFlat             = true;
input int    InpMaxSpreadPoints         = 0;
input int    InpDeviationPoints         = 20;
input int    InpMagicNumber             = 260621;

CTrade  ExtTrade;
CSpaceSonarTradeShapeKpi ExtTradeShape;
int     ExtExecutionHandle = INVALID_HANDLE;
datetime ExtLastClosedBarTime = 0;
datetime ExtEntryCloseTime = 0;
int     ExtRowsLoaded = 0;
int     ExtRowsObserved = 0;
int     ExtOrdersAttempted = 0;
int     ExtReplayBarIndex = 0;
datetime ExtTelemetryTimes[];
double  ExtTelemetryScores[];
string  ExtTelemetryDecisions[];
bool    ExtTrackedPosition = false;
bool    ExtTrackedIsLong = false;
datetime ExtTrackedEntryTime = 0;
int     ExtTrackedEntryBarIndex = 0;
double  ExtTrackedEntryPrice = 0.0;
double  ExtTrackedMaxFavorable = 0.0;
double  ExtTrackedMaxAdverse = 0.0;
double  ExtTrackedSpreadEntry = 0.0;
ulong   ExtTrackedTicket = 0;

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
   if(InpDirectionPolicy == "score_band_side")
      return "flat";
   if(InpDirectionPolicy == "score_band_inverse_side")
      return "flat";
   return "flat";
}

bool IsScoreBandDirectionalFamily()
{
   if(InpDecisionFamily == "abstain_band_with_barrier_exit")
      return true;
   if(InpDecisionFamily == "breakout_entry_abstain_timeout_exit")
      return true;
   if(InpDecisionFamily == "reversal_entry_abstain_timeout_exit")
      return true;
   if(InpDecisionFamily == "mean_reversion_abstain_barrier_exit")
      return true;
   if(InpDecisionFamily == "sparse_event_abstain_barrier_exit")
      return true;
   if(InpDecisionFamily == "fast_event_abstain_timeout_exit")
      return true;
   if(InpDecisionFamily == "session_gated_abstain_barrier_exit")
      return true;
   if(InpDecisionFamily == "range_edge_abstain_timeout_exit")
      return true;
   if(InpDecisionFamily == "failed_breakout_reversion_abstain_exit")
      return true;
   if(InpDecisionFamily == "abstain_timeout_h6")
      return true;
   if(InpDecisionFamily == "abstain_timeout_h12")
      return true;
   if(InpDecisionFamily == "adverse_excursion_stop")
      return true;
   if(InpDecisionFamily == "open_failed_abstain_gate")
      return true;
   if(InpDecisionFamily == "session_abstain_timeout")
      return true;
   if(InpDecisionFamily == "volatility_stop_timeout")
      return true;
   return false;
}

bool IsDiagnosticOrNoTradeFamily()
{
   if(InpDecisionFamily == "diagnostic_rank_only")
      return true;
   if(InpDecisionFamily == "no_trade_vs_fast_event_abstain")
      return true;
   if(InpDecisionFamily == "no_trade_regime_filter")
      return true;
   if(InpDecisionFamily == "diagnostic_path_quality_no_trade_until_decision_surface")
      return true;
   return false;
}

string ExecutionSignal(const string source_decision, const double score)
{
   const string decision = source_decision;
   if(IsScoreBandDirectionalFamily())
   {
      if(score >= InpScoreHigh)
      {
         if(InpDirectionPolicy == "score_band_inverse_side")
            return "short";
         return "long";
      }
      if(score <= InpScoreLow)
      {
         if(InpDirectionPolicy == "score_band_inverse_side")
            return "long";
         return "short";
      }
      return "flat";
   }
   if(IsDiagnosticOrNoTradeFamily())
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

void ResetTrackedPosition()
{
   ExtTrackedPosition = false;
   ExtTrackedIsLong = false;
   ExtTrackedEntryTime = 0;
   ExtTrackedEntryBarIndex = 0;
   ExtTrackedEntryPrice = 0.0;
   ExtTrackedMaxFavorable = 0.0;
   ExtTrackedMaxAdverse = 0.0;
   ExtTrackedSpreadEntry = 0.0;
   ExtTrackedTicket = 0;
}

void TrackOpenedPosition(const string signal, const datetime close_time, const int bar_index)
{
   ENUM_POSITION_TYPE position_type;
   if(!HasOurPosition(position_type))
      return;

   ExtTrackedPosition = true;
   ExtTrackedIsLong = (position_type == POSITION_TYPE_BUY);
   ExtTrackedEntryTime = close_time;
   ExtTrackedEntryBarIndex = bar_index;
   ExtTrackedEntryPrice = PositionGetDouble(POSITION_PRICE_OPEN);
   ExtTrackedMaxFavorable = 0.0;
   ExtTrackedMaxAdverse = 0.0;
   ExtTrackedSpreadEntry = (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD);
   ExtTrackedTicket = (ulong)PositionGetInteger(POSITION_TICKET);
   if(ExtTrackedEntryPrice <= 0.0)
      ExtTrackedEntryPrice = (signal == "long" ? SymbolInfoDouble(_Symbol, SYMBOL_ASK) : SymbolInfoDouble(_Symbol, SYMBOL_BID));
}

void UpdateTrackedExcursion()
{
   if(!ExtTrackedPosition || ExtTrackedEntryPrice <= 0.0)
      return;

   const double point_value = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point_value <= 0.0)
      return;
   const double high_value = iHigh(_Symbol, PERIOD_M5, 1);
   const double low_value = iLow(_Symbol, PERIOD_M5, 1);
   if(high_value <= 0.0 || low_value <= 0.0)
      return;

   double favorable = 0.0;
   double adverse = 0.0;
   if(ExtTrackedIsLong)
   {
      favorable = (high_value - ExtTrackedEntryPrice) / point_value;
      adverse = (ExtTrackedEntryPrice - low_value) / point_value;
   }
   else
   {
      favorable = (ExtTrackedEntryPrice - low_value) / point_value;
      adverse = (high_value - ExtTrackedEntryPrice) / point_value;
   }
   ExtTrackedMaxFavorable = MathMax(ExtTrackedMaxFavorable, favorable);
   ExtTrackedMaxAdverse = MathMax(ExtTrackedMaxAdverse, adverse);
}

void EmitTrackedClose(const string exit_reason, const datetime close_time, const int bar_index, const double exit_price)
{
   if(!ExtTrackedPosition || !InpEmitTradeShapeTelemetry || !ExtTradeShape.IsOpen())
      return;

   ExtTradeShape.RecordClosedTrade(
      ExtTrackedTicket,
      ExtTrackedIsLong,
      ExtTrackedEntryTime,
      ExtTrackedEntryBarIndex,
      ExtTrackedEntryPrice,
      close_time,
      bar_index,
      exit_price,
      exit_reason,
      ExtTrackedMaxFavorable,
      ExtTrackedMaxAdverse,
      0.0,
      ExtTrackedSpreadEntry,
      (double)SymbolInfoInteger(_Symbol, SYMBOL_SPREAD)
   );
}

bool CloseOurPosition(const string exit_reason, const datetime close_time, const int bar_index)
{
   ENUM_POSITION_TYPE position_type;
   if(!HasOurPosition(position_type))
      return true;
   const double exit_price = (position_type == POSITION_TYPE_BUY ? SymbolInfoDouble(_Symbol, SYMBOL_BID) : SymbolInfoDouble(_Symbol, SYMBOL_ASK));
   ResetLastError();
   const bool closed = ExtTrade.PositionClose(_Symbol);
   if(!closed)
      PrintFormat("Score replay close failed err=%d", GetLastError());
   if(closed)
   {
      EmitTrackedClose(exit_reason, close_time, bar_index, exit_price);
      ExtEntryCloseTime = 0;
      ResetTrackedPosition();
   }
   return closed;
}

string ApplySignal(const datetime close_time, const string signal, const int bar_index)
{
   ENUM_POSITION_TYPE position_type;
   const bool has_position = HasOurPosition(position_type);
   if(has_position && ExtEntryCloseTime > 0 && InpHoldBars > 0)
   {
      const int elapsed = (int)((close_time - ExtEntryCloseTime) / PeriodSeconds(PERIOD_M5));
      if(elapsed >= InpHoldBars)
      {
         CloseOurPosition("close_hold_elapsed", close_time, bar_index);
         return "close_hold_elapsed";
      }
   }

   if(signal == "flat")
   {
      if(InpCloseOnFlat && has_position)
      {
         CloseOurPosition("close_flat", close_time, bar_index);
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
      CloseOurPosition("implicit_reversal", close_time, bar_index);
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
   TrackOpenedPosition(signal, close_time, bar_index);
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
   if(InpEmitTradeShapeTelemetry)
   {
      const string attempt_id = (StringLen(InpAttemptId) > 0 ? InpAttemptId : InpTradeShapeTelemetryPath);
      if(!ExtTradeShape.Open(attempt_id, InpTradeShapeTelemetryPath, InpUseCommonFiles))
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
   ExtTradeShape.Close();
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
   ExtReplayBarIndex++;
   UpdateTrackedExcursion();
   const string action = ApplySignal(close_time, signal, ExtReplayBarIndex);
   WriteExecutionRow(close_time, score, source_decision, signal, action);
   ExtRowsObserved++;
}
