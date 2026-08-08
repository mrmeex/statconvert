export interface FormatOption {
  value: string;
  label: string;
}

const formatLabels: Record<string, string> = {
  csv: "CSV (*.csv)",
  dta: "Stata (*.dta)",
  feather: "Feather (*.feather)",
  html: "HTML (*.html)",
  json: "JSON (*.json)",
  jsonl: "JSON Lines (*.jsonl)",
  ndjson: "Newline-delimited JSON (*.ndjson)",
  ods: "ODS (*.ods)",
  parquet: "Parquet (*.parquet)",
  por: "SPSS Portable (*.por)",
  rda: "RData / RDA (*.rdata, *.rda)",
  rdata: "RData / RDA (*.rdata, *.rda)",
  rds: "RDS (*.rds)",
  sas7bdat: "SAS Data Set (*.sas7bdat)",
  sav: "SPSS (*.sav)",
  xls: "Excel 97–2003 (*.xls)",
  xlsx: "Excel (*.xlsx)",
  xpt: "SAS Transport / XPT (*.xpt)",
  zsav: "SPSS Compressed (*.zsav)",
};

export function formatOptions(values: readonly string[]): FormatOption[] {
  return values
    .map((value) => ({
      value,
      label: formatLabels[value] ?? `${value.toUpperCase()} (*.${value})`,
    }))
    .sort((left, right) => left.label.localeCompare(right.label));
}
