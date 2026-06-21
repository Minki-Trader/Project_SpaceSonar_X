//+------------------------------------------------------------------+
//| SpaceSonar ONNX Fixed-Fixture Probe                              |
//| Non-trading EA: loads one ONNX bundle and compares one fixture.   |
//+------------------------------------------------------------------+
#property strict
#property version   "1.00"
#property description "Non-trading MT5 native ONNX fixed-fixture probe for SpaceSonar X."

input string InpOnnxPath           = "SpaceSonar\\onnx_fixture\\bundle_fixture\\model.onnx";
input string InpFixtureInputPath   = "SpaceSonar\\onnx_fixture\\bundle_fixture\\fixture_input.csv";
input string InpExpectedOutputPath = "SpaceSonar\\onnx_fixture\\bundle_fixture\\expected_output.csv";
input string InpOutputPath         = "SpaceSonar\\onnx_fixture\\bundle_fixture\\mt5_probe_output.csv";
input int    InpFeatureCount       = 4;
input double InpTolerance          = 0.00001;
input bool   InpUseCommonFiles     = true;
input bool   InpRemoveAfterRun     = true;

bool ReadVectorCsv(const string path, vectorf &values, const int expected_count)
{
   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   const int handle = FileOpen(path, FILE_READ | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("fixture open failed path=%s err=%d", path, GetLastError());
      return false;
   }

   values.Resize((ulong)expected_count);
   for(int i = 0; i < expected_count; i++)
   {
      if(FileIsEnding(handle))
      {
         FileClose(handle);
         PrintFormat("fixture file ended early path=%s index=%d", path, i);
         return false;
      }
      values[i] = (float)FileReadNumber(handle);
   }
   FileClose(handle);
   return true;
}

bool ReadExpectedCsv(const string path, double &expected)
{
   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   const int handle = FileOpen(path, FILE_READ | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("expected output open failed path=%s err=%d", path, GetLastError());
      return false;
   }
   expected = FileReadNumber(handle);
   FileClose(handle);
   return true;
}

void WriteProbeOutput(const string status,
                      const int input_count,
                      const int output_count,
                      const double expected,
                      const double observed,
                      const double abs_error,
                      const int last_error)
{
   const int common_flag = (InpUseCommonFiles ? FILE_COMMON : 0);
   ResetLastError();
   const int handle = FileOpen(InpOutputPath, FILE_WRITE | FILE_CSV | FILE_ANSI | common_flag, ',');
   if(handle == INVALID_HANDLE)
   {
      PrintFormat("probe output open failed path=%s err=%d", InpOutputPath, GetLastError());
      return;
   }

   FileWrite(handle,
             "status",
             "input_count",
             "output_count",
             "expected_probability",
             "mt5_probability",
             "abs_error",
             "tolerance",
             "last_error");
   FileWrite(handle,
             status,
             input_count,
             output_count,
             DoubleToString(expected, 10),
             DoubleToString(observed, 10),
             DoubleToString(abs_error, 10),
             DoubleToString(InpTolerance, 10),
             last_error);
   FileClose(handle);
}

bool RunProbe()
{
   if(InpFeatureCount <= 0)
   {
      Print("InpFeatureCount must be positive.");
      return false;
   }

   vectorf fixture_values;
   double expected = 0.0;
   if(!ReadVectorCsv(InpFixtureInputPath, fixture_values, InpFeatureCount))
      return false;
   if(!ReadExpectedCsv(InpExpectedOutputPath, expected))
      return false;

   const uint flags = (uint)((InpUseCommonFiles ? ONNX_COMMON_FOLDER : 0) | ONNX_LOGLEVEL_INFO | ONNX_USE_CPU_ONLY);
   ResetLastError();
   const long handle = OnnxCreate(InpOnnxPath, flags);
   if(handle == INVALID_HANDLE || handle == 0)
   {
      const int err = GetLastError();
      PrintFormat("OnnxCreate failed path=%s err=%d", InpOnnxPath, err);
      WriteProbeOutput("onnx_create_failed", -1, -1, expected, 0.0, 0.0, err);
      return false;
   }

   const long input_count = OnnxGetInputCount(handle);
   const long output_count = OnnxGetOutputCount(handle);
   ulong input_shape[1];
   ulong output_shape[1];
   input_shape[0] = (ulong)InpFeatureCount;
   output_shape[0] = 1;

   if(!OnnxSetInputShape(handle, 0, input_shape))
   {
      const int err = GetLastError();
      PrintFormat("OnnxSetInputShape failed err=%d", err);
      WriteProbeOutput("input_shape_failed", (int)input_count, (int)output_count, expected, 0.0, 0.0, err);
      OnnxRelease(handle);
      return false;
   }

   if(!OnnxSetOutputShape(handle, 0, output_shape))
   {
      const int err = GetLastError();
      PrintFormat("OnnxSetOutputShape failed err=%d", err);
      WriteProbeOutput("output_shape_failed", (int)input_count, (int)output_count, expected, 0.0, 0.0, err);
      OnnxRelease(handle);
      return false;
   }

   vectorf output(1);
   ResetLastError();
   if(!OnnxRun(handle, ONNX_NO_CONVERSION | ONNX_LOGLEVEL_INFO, fixture_values, output))
   {
      const int err = GetLastError();
      PrintFormat("OnnxRun failed err=%d", err);
      WriteProbeOutput("onnx_run_failed", (int)input_count, (int)output_count, expected, 0.0, 0.0, err);
      OnnxRelease(handle);
      return false;
   }

   const double observed = (double)output[0];
   const double abs_error = MathAbs(observed - expected);
   const string status = (abs_error <= InpTolerance ? "matched" : "mismatch");
   WriteProbeOutput(status, (int)input_count, (int)output_count, expected, observed, abs_error, 0);
   PrintFormat("SpaceSonar ONNX fixture probe status=%s expected=%.10f observed=%.10f abs_error=%.10f tolerance=%.10f",
               status, expected, observed, abs_error, InpTolerance);

   OnnxRelease(handle);
   return (status == "matched");
}

int OnInit()
{
   const bool ok = RunProbe();
   if(InpRemoveAfterRun)
      ExpertRemove();
   return (ok ? INIT_SUCCEEDED : INIT_FAILED);
}
