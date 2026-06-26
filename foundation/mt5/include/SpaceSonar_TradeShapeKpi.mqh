//+------------------------------------------------------------------+
//| SpaceSonar Trade Shape KPI include                               |
//| Emits raw trade-shape telemetry; Python summaries provide authority. |
//+------------------------------------------------------------------+
#ifndef SPACESONAR_TRADE_SHAPE_KPI_MQH
#define SPACESONAR_TRADE_SHAPE_KPI_MQH

double SpaceSonarSignedPoints(
   const bool is_long,
   const double entry_price,
   const double exit_price,
   const double point_value
)
{
   if(point_value <= 0.0)
      return 0.0;
   if(is_long)
      return (exit_price - entry_price) / point_value;
   return (entry_price - exit_price) / point_value;
}

double SpaceSonarExitEfficiency(const double gross_points, const double mfe_points)
{
   if(mfe_points <= 0.0)
      return 0.0;
   return gross_points / mfe_points;
}

class CSpaceSonarTradeShapeKpi
{
private:
   int    m_handle;
   bool   m_use_common_files;
   string m_output_path;
   string m_attempt_id;
   string m_formula_version;

public:
   CSpaceSonarTradeShapeKpi()
   {
      m_handle = INVALID_HANDLE;
      m_use_common_files = true;
      m_output_path = "";
      m_attempt_id = "";
      m_formula_version = "trade_shape_kpi_v1";
   }

   bool Open(const string attempt_id, const string output_path, const bool use_common_files)
   {
      m_attempt_id = attempt_id;
      m_output_path = output_path;
      m_use_common_files = use_common_files;
      const int common_flag = (m_use_common_files ? FILE_COMMON : 0);
      ResetLastError();
      m_handle = FileOpen(m_output_path, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
      if(m_handle == INVALID_HANDLE)
      {
         PrintFormat("SpaceSonar trade-shape KPI open failed path=%s err=%d", m_output_path, GetLastError());
         return false;
      }
      WriteHeader();
      return true;
   }

   void Close()
   {
      if(m_handle != INVALID_HANDLE)
      {
         FileClose(m_handle);
         m_handle = INVALID_HANDLE;
      }
   }

   bool IsOpen() const
   {
      return (m_handle != INVALID_HANDLE);
   }

   void WriteHeader()
   {
      if(m_handle == INVALID_HANDLE)
         return;
      FileWrite(
         m_handle,
         "attempt_id",
         "symbol",
         "timeframe",
         "position_id_or_ticket",
         "side",
         "entry_time",
         "entry_bar_index",
         "entry_price",
         "exit_time",
         "exit_bar_index",
         "exit_price",
         "exit_reason",
         "hold_bars",
         "max_favorable_points",
         "max_adverse_points",
         "mfe_points",
         "mae_points",
         "gross_points",
         "initial_risk_points",
         "mfe_r",
         "mae_r",
         "gross_r",
         "exit_efficiency",
         "spread_points_entry",
         "spread_points_exit",
         "digits",
         "point",
         "tick_size",
         "formula_version"
      );
   }

   void RecordClosedTrade(
      const ulong position_id_or_ticket,
      const bool is_long,
      const datetime entry_time,
      const int entry_bar_index,
      const double entry_price,
      const datetime exit_time,
      const int exit_bar_index,
      const double exit_price,
      const string exit_reason,
      const double max_favorable_points,
      const double max_adverse_points,
      const double initial_risk_points,
      const double spread_points_entry,
      const double spread_points_exit
   )
   {
      if(m_handle == INVALID_HANDLE)
         return;

      const double point_value = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
      const double tick_size = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
      const int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
      const double gross_points = SpaceSonarSignedPoints(is_long, entry_price, exit_price, point_value);
      const double mfe_points = max_favorable_points;
      const double mae_points = max_adverse_points;
      const double mfe_r = (initial_risk_points > 0.0 ? mfe_points / initial_risk_points : 0.0);
      const double mae_r = (initial_risk_points > 0.0 ? mae_points / initial_risk_points : 0.0);
      const double gross_r = (initial_risk_points > 0.0 ? gross_points / initial_risk_points : 0.0);
      const double exit_efficiency = SpaceSonarExitEfficiency(gross_points, mfe_points);
      const int hold_bars = exit_bar_index - entry_bar_index;

      FileWrite(
         m_handle,
         m_attempt_id,
         _Symbol,
         EnumToString(_Period),
         (string)position_id_or_ticket,
         (is_long ? "long" : "short"),
         TimeToString(entry_time, TIME_DATE | TIME_SECONDS),
         entry_bar_index,
         DoubleToString(entry_price, digits),
         TimeToString(exit_time, TIME_DATE | TIME_SECONDS),
         exit_bar_index,
         DoubleToString(exit_price, digits),
         exit_reason,
         hold_bars,
         DoubleToString(max_favorable_points, 5),
         DoubleToString(max_adverse_points, 5),
         DoubleToString(mfe_points, 5),
         DoubleToString(mae_points, 5),
         DoubleToString(gross_points, 5),
         DoubleToString(initial_risk_points, 5),
         DoubleToString(mfe_r, 8),
         DoubleToString(mae_r, 8),
         DoubleToString(gross_r, 8),
         DoubleToString(exit_efficiency, 8),
         DoubleToString(spread_points_entry, 5),
         DoubleToString(spread_points_exit, 5),
         digits,
         DoubleToString(point_value, digits),
         DoubleToString(tick_size, digits),
         m_formula_version
      );
   }
};

#endif

