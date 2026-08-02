import {
  Badge,
  Box,
  Button,
  Group,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";

import {
  navigationItems,
  type NavigationItem,
} from "../routes/navigation";

interface HomePageProps {
  onNavigate: (page: NavigationItem) => void;
}

const featuredPages = navigationItems.filter((item) =>
  ["inspect", "convert", "batch", "validate", "transform", "configs", "compare", "report", "collect", "reference"].includes(
    item.id,
  ),
);

export function HomePage({ onNavigate }: HomePageProps) {
  return (
    <Box className="page-content">
      <Paper className="hero-card" radius="xl">
        <Stack gap="md" maw={720}>
          <Title order={1}>Move statistical data with confidence.</Title>
          <Text size="lg" c="dimmed">
            Inspect, convert, validate, transform, compare, report, and collect
            datasets locally. Files stay on your machine, with reusable configs
            and equivalent commands available when you need them.
          </Text>
          <Group>
            <Button
              size="md"
              onClick={() =>
                onNavigate(navigationItems.find((item) => item.id === "inspect")!)
              }
            >
              Inspect a dataset
            </Button>
            <Text size="sm" c="dimmed">
              Local preferences and runtime details are available in Settings and About.
            </Text>
          </Group>
        </Stack>
      </Paper>

      <Group justify="space-between" mt={40} mb="lg">
        <Title order={2}>Choose a workflow</Title>
        <Badge variant="outline" color="gray">
          1.0.0g5
        </Badge>
      </Group>

      <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }} spacing="lg">
        {featuredPages.map((page) => {
          const Icon = page.icon;
          return (
          <Paper
            key={page.id}
            withBorder
            p="xl"
            radius="lg"
            className="workflow-card"
          >
            <Group justify="space-between" align="flex-start">
              <span className="workflow-icon" aria-hidden="true">
                <Icon size={23} stroke={1.8} />
              </span>
              <Badge variant="light">{page.slice}</Badge>
            </Group>
            <Title order={3} mt="lg">
              {page.label}
            </Title>
            <Text c="dimmed" mt="xs" mih={52}>
              {page.description}
            </Text>
            <Button
              variant="subtle"
              px={0}
              mt="md"
              onClick={() => onNavigate(page)}
            >
              Open workflow →
            </Button>
          </Paper>
          );
        })}
      </SimpleGrid>
    </Box>
  );
}
