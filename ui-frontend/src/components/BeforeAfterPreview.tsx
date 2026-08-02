import { Grid, Paper, Text, Title } from "@mantine/core";

import type { TransformPreviewResponse } from "../lib/types";
import { ResultView } from "./ResultView";

export function BeforeAfterPreview({ preview }: { preview: TransformPreviewResponse["data"] | null }) {
  if (!preview) return null;
  return <Paper withBorder radius="lg" p="lg">
    <Title order={3}>Before / after preview</Title>
    <Text size="sm" c="dimmed" mb="md">Sampled {preview.sampled_rows} of {preview.rows_before} rows; the preview never writes the output file.</Text>
    <Grid>
      <Grid.Col span={{ base: 12, xl: 6 }}><ResultView title="Before" data={{ rows: preview.before_rows }} /></Grid.Col>
      <Grid.Col span={{ base: 12, xl: 6 }}><ResultView title={`After · ${preview.preview_rows} rows`} data={{ rows: preview.sample_output_rows }} /></Grid.Col>
    </Grid>
  </Paper>;
}
