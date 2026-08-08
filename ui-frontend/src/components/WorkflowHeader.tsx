import { Box, Text, Title } from "@mantine/core";

interface WorkflowHeaderProps {
  title: string;
  description: string;
}

export function WorkflowHeader({
  title,
  description,
}: WorkflowHeaderProps) {
  return (
    <Box mb="xl">
      <Title order={1}>{title}</Title>
      <Text c="dimmed" mt="xs" maw={760}>
        {description}
      </Text>
    </Box>
  );
}
