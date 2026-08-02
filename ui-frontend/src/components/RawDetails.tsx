import { Box, Code, Text } from "@mantine/core";

interface RawDetailsProps {
  data: unknown;
}

export function RawDetails({ data }: RawDetailsProps) {
  if (data === null || data === undefined) return null;
  return (
    <Box component="details" mt="lg" className="raw-details">
      <Text component="summary" size="sm" fw={600} c="dimmed" style={{ cursor: "pointer" }}>
        Raw details
      </Text>
      <Code block className="json-result" mt="sm">{JSON.stringify(data, null, 2)}</Code>
    </Box>
  );
}
