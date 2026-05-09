import { useWizardState } from "@/hooks/useWizardState";
import { StepIndicator } from "./StepIndicator";
import { Step1Upload } from "./steps/Step1Upload";
import { Step2Variables } from "./steps/Step2Variables";
import { Step3ModelSettings } from "./steps/Step3ModelSettings";
import { Step4TrainTest } from "./steps/Step4TrainTest";
import { Step5HardRules } from "./steps/Step5HardRules";
import { Step6SoftRules } from "./steps/Step6SoftRules";
import { Step7Review } from "./steps/Step7Review";
import { Button } from "@/components/ui/button";
import { ArrowLeft, ArrowRight } from "lucide-react";

export function ConfigWizard() {
  const state = useWizardState();

  const renderStep = () => {
    switch (state.step) {
      case 0: return <Step1Upload columns={state.columns} setColumns={state.setColumns} runConfig={state.runConfig} updateRun={state.updateRun} />;
      case 1: return <Step2Variables columns={state.columns} basicConfig={state.basicConfig} runConfig={state.runConfig} updateBasic={state.updateBasic} />;
      case 2: return <Step3ModelSettings basicConfig={state.basicConfig} updateBasic={state.updateBasic} />;
      case 3: return <Step4TrainTest basicConfig={state.basicConfig} updateBasic={state.updateBasic} />;
      case 4: return <Step5HardRules basicConfig={state.basicConfig} runConfig={state.runConfig} updateRun={state.updateRun} />;
      case 5: return <Step6SoftRules runConfig={state.runConfig} updateRun={state.updateRun} />;
      case 6: return <Step7Review basicConfig={state.basicConfig} runConfig={state.runConfig} onReset={state.reset} />;
      default: return null;
    }
  };

  return (
    <div className="min-h-screen bg-background py-8 px-4">
      <div className="max-w-3xl mx-auto space-y-6">
        <header className="text-center space-y-2">
          <h1 className="text-3xl font-bold tracking-tight text-foreground">ARIMAX Config Wizard</h1>
          <p className="text-muted-foreground">Build your configuration step by step</p>
        </header>

        <StepIndicator currentStep={state.step} onStepClick={state.setStep} />

        {renderStep()}

        <div className="flex justify-between pt-2">
          <Button variant="outline" onClick={state.back} disabled={state.step === 0} className="gap-2">
            <ArrowLeft className="w-4 h-4" /> Back
          </Button>
          {state.step < 6 && (
            <Button onClick={state.next} className="gap-2">
              Next <ArrowRight className="w-4 h-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
