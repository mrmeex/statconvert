export interface FormatOption {
  value: string;
  label: string;
}

const formatLabels: Record<string, string> = {
  csv: "CSV (*.csv)",
  dta: "Stata (*.dta)",
  feather: "Apache Feather (*.feather)",
  html: "HTML (*.html)",
  json: "JSON (*.json)",
  jsonl: "JSON Lines (*.jsonl)",
  ndjson: "Newline-delimited JSON (*.ndjson)",
  ods: "OpenDocument Spreadsheet (*.ods)",
  parquet: "Apache Parquet (*.parquet)",
  por: "SPSS Portable (*.por)",
  rda: "RData (*.rda)",
  rdata: "RData (*.rdata)",
  rds: "RDS (*.rds)",
  sas7bdat: "SAS Data Set (*.sas7bdat)",
  sav: "SPSS SAV (*.sav)",
  xls: "Excel 97-2003 Workbook (*.xls)",
  xlsx: "Excel Workbook (*.xlsx)",
  xpt: "SAS XPORT (*.xpt)",
  zsav: "SPSS Compressed (ZSAV) (*.zsav)",
};

export const writableFormatValues = [
  "csv", "dta", "feather", "json", "jsonl", "ndjson", "ods", "parquet",
  "rda", "rdata", "rds", "sav", "xls", "xlsx", "xpt",
] as const;

export function formatOptions(values: readonly string[]): FormatOption[] {
  return values
    .map((value) => ({
      value,
      label: formatLabels[value] ?? `${value.toUpperCase()} (*.${value})`,
    }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

export const writableFormatOptions = formatOptions(writableFormatValues);
