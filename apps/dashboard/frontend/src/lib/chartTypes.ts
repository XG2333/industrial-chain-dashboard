export interface ChartPoint {
  date: string;
  value: number;
}

export interface ChartTag {
  category: string;
  value: string;
}

export interface ChartMeta {
  id: string;
  catalogOrder?: number;
  title: string;
  unit: string;
  category: string;
  section?: string;
  source: string;
  freq?: string;
  confidence?: number;
  major?: string;
  sub?: string;
  sector?: string;
  displayBlockTag?: string;
  selected?: boolean;
  finalSelected?: boolean;
  selection_reason?: string;
  tags?: ChartTag[];
}

export interface ChartData extends ChartMeta {
  data: ChartPoint[];
}
