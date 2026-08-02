import {
  Badge,
  Box,
  Paper,
  Stack,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";

import type { NavigationItem } from "../routes/navigation";

interface PlaceholderPageProps {
  page: NavigationItem;
}

export function PlaceholderPage({ page }: PlaceholderPageProps) {
  const Icon = page.icon;
  return (
    <Box className="page-content">
      <Paper withBorder radius="xl" p={48} className="placeholder-card">
        <Stack align="flex-start" gap="lg">
          <ThemeIcon size={56} radius="lg" variant="light">
            <Icon size={28} stroke={1.8} />
          </ThemeIcon>
          <Badge variant="light">
            {page.slice}
          </Badge>
          <Title order={1}>{page.label}</Title>
          <Text size="lg" c="dimmed" maw={680}>
            {page.description}
          </Text>
          <Text className="coming-soon">
            This page is registered in the local StatConvert workspace.
          </Text>
        </Stack>
      </Paper>
    </Box>
  );
}
