-- Create table for saved ARIMAX configs (public, no auth required)
CREATE TABLE public.arimax_configs (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  payload JSONB NOT NULL,
  title TEXT,
  notes TEXT,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.arimax_configs ENABLE ROW LEVEL SECURITY;

-- Allow anyone to insert configs (no auth required for this wizard)
CREATE POLICY "Anyone can insert configs"
  ON public.arimax_configs
  FOR INSERT
  WITH CHECK (true);

-- Allow anyone to read configs (for share links)
CREATE POLICY "Anyone can read configs"
  ON public.arimax_configs
  FOR SELECT
  USING (true);