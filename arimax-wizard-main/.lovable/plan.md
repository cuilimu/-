
# ARIMAX Config Wizard — Friendly Step-by-Step UI

A guided, wizard-style interface that walks users through configuring their ARIMAX automation engine and exports a ready-to-use JSON config file.

---

## Step 1: Upload Your Data
- **CSV file upload** — the UI reads column headers automatically
- Auto-detected columns populate dropdowns in subsequent steps
- User selects the **date column** (`ds_column`) from a dropdown
- User specifies the **file path string** to embed in the exported JSON (so Python can find the file)

## Step 2: Target & Exogenous Variables
- **Select TARGET variable** — dropdown populated from uploaded CSV columns
- **Select MEVS** (exogenous variables) — multi-select checklist from remaining columns
- **MEVS_Guide** — for each selected MEV, choose a transformation method from a dropdown: `log_diff`, `diff`, or `none`
- Clean summary table showing each MEV and its assigned transformation

## Step 3: Model Settings (Basic Config)
- **Frequency** — select from common options: `QE` (quarterly), `ME` (monthly), `W`, `D`, etc.
- **Max Lag** — number input (e.g. 1–12)
- **Max Exogenous Variables** — number input (default: 2)
- **Transform** — select: `original`, `log`, `diff`, `log_diff`
- **Include Non-Lags** — toggle switch (default: off)
- **Trace / Use tqdm** — toggle switches for developer options

## Step 4: Train/Test Split
- **Train Threshold** — slider from 0.5 to 0.95 (default: 0.8), with a visual bar showing the train/test split
- **OOT Test** — toggle switch; when enabled, reveals:
  - **OOT Threshold** — slider (default: 0.9)

## Step 5: Hard Rules (Run Config)
- **Expected Sign** — for each selected MEV, choose `+`, `-`, or `undetermined` from a dropdown
- **Alpha** — number input (default: 0.05)
- **Enforce Significance For** — optional multi-select of MEVs
- **Require Stationary / Invertible** — toggle switches (default: on)
- **Max Absolute AR / MA** — optional number inputs
- **VIF Max** — optional number input
- **Apply Hard Rules** — master toggle (default: on); when off, the section grays out

## Step 6: Soft Rules & Ranking
- **Soft Method** — select from: `weighted`, `mse`, `mae`, `rmse`, `mape`, `smape`, `mase`
- **Top N** — number input (default: 3)
- **Weights** — optional; if `weighted` is selected, show inputs to assign custom weights

## Step 7: Review & Export
- **Full JSON preview** in a formatted code block, showing the complete config
- **Edit inline** — users can tweak the JSON directly if needed
- **Two export options:**
  - 📋 **Copy to Clipboard** button
  - 📥 **Download as .json** button
- **Reset** button to start over

---

## Design & UX Details
- **Progress indicator** at the top showing all 7 steps with current position
- **Back / Next navigation** between steps
- **Friendly tooltips** on every field explaining what it does in plain language
- **Smart defaults** pre-filled so users can skip to Review quickly
- **Validation** — required fields are highlighted, numeric ranges are enforced
- **Clean, welcoming color palette** with card-based layout for each section
