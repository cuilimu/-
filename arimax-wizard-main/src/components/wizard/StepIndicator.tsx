import { cn } from "@/lib/utils";
import { Check } from "lucide-react";

const STEP_LABELS = [
  "Upload Data",
  "Variables",
  "Model Settings",
  "Train/Test",
  "Hard Rules",
  "Soft Rules",
  "Review",
];

interface StepIndicatorProps {
  currentStep: number;
  onStepClick: (step: number) => void;
}

export function StepIndicator({ currentStep, onStepClick }: StepIndicatorProps) {
  return (
    <div className="flex items-center justify-between w-full max-w-3xl mx-auto mb-8">
      {STEP_LABELS.map((label, i) => {
        const done = i < currentStep;
        const active = i === currentStep;
        return (
          <div key={i} className="flex flex-col items-center gap-1.5 flex-1">
            <button
              onClick={() => onStepClick(i)}
              className={cn(
                "w-9 h-9 rounded-full flex items-center justify-center text-sm font-semibold transition-all border-2",
                done && "bg-primary border-primary text-primary-foreground",
                active && "border-primary text-primary bg-background shadow-md",
                !done && !active && "border-muted-foreground/30 text-muted-foreground bg-background"
              )}
            >
              {done ? <Check className="w-4 h-4" /> : i + 1}
            </button>
            <span className={cn(
              "text-xs font-medium text-center hidden sm:block",
              active ? "text-primary" : "text-muted-foreground"
            )}>
              {label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
