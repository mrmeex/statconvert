import { Badge, Box, Group, Text, Title } from "@mantine/core";

interface WorkflowHeaderProps {
  title: string;
  description: string;
  badge?: string;
}

export function WorkflowHeader({
  title,
  description,
  badge = "1.0.0c",
}: WorkflowHeaderProps) {
  return (
    <Group justify="space-between" align="flex-start" mb="xl">
      <Box>
        <Title order={1}>{title}</Title>
        <Text c="dimmed" mt="xs" maw={760}>
          {description}
        </Text>
      </Box>
      <Badge variant="light" size="lg">
        {badge}
      </Badge>
    </Group>
  );
}
