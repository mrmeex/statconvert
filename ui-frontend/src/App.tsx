import { useMemo, useState } from "react";
import {
  AppShell,
  Badge,
  Box,
  Burger,
  Group,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";

import { ApiStatus } from "./components/ApiStatus";
import { SidebarNavigation } from "./components/SidebarNavigation";
import { BatchPage } from "./pages/BatchPage";
import { AboutPage } from "./pages/AboutPage";
import { CollectPage } from "./pages/CollectPage";
import { ComparePage } from "./pages/ComparePage";
import { ConfigsPage } from "./pages/ConfigsPage";
import { ConvertPage } from "./pages/ConvertPage";
import { HomePage } from "./pages/HomePage";
import { InspectPage } from "./pages/InspectPage";
import { PlaceholderPage } from "./pages/PlaceholderPage";
import { ReferencePage } from "./pages/ReferencePage";
import { ReportPage } from "./pages/ReportPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ValidatePage } from "./pages/ValidatePage";
import { TransformPage } from "./pages/TransformPage";
import {
  navigationItems,
  type NavigationItem,
  type PageId,
} from "./routes/navigation";

function App() {
  const [activePage, setActivePage] = useState<PageId>("home");
  const [opened, { toggle, close }] = useDisclosure();
  const currentPage = useMemo(
    () => navigationItems.find((item) => item.id === activePage)!,
    [activePage],
  );

  const selectPage = (page: NavigationItem) => {
    setActivePage(page.id);
    close();
  };

  const pageContent = () => {
    switch (activePage) {
      case "home":
        return <HomePage onNavigate={selectPage} />;
      case "inspect":
        return <InspectPage />;
      case "convert":
        return <ConvertPage />;
      case "batch":
        return <BatchPage />;
      case "validate":
        return <ValidatePage />;
      case "transform":
        return <TransformPage />;
      case "configs":
        return <ConfigsPage />;
      case "compare":
        return <ComparePage />;
      case "report":
        return <ReportPage />;
      case "collect":
        return <CollectPage />;
      case "reference":
        return <ReferencePage />;
      case "settings":
        return <SettingsPage />;
      case "about":
        return <AboutPage />;
      default:
        return <PlaceholderPage page={currentPage} />;
    }
  };

  return (
    <AppShell
      header={{ height: 64 }}
      navbar={{
        width: 284,
        breakpoint: "md",
        collapsed: { mobile: !opened },
      }}
      padding={0}
    >
      <AppShell.Header className="topbar">
        <Group h="100%" px="xl" justify="space-between">
          <Group gap="md">
            <Burger
              opened={opened}
              onClick={toggle}
              hiddenFrom="md"
              size="sm"
              aria-label="Toggle navigation"
            />
            <Title order={2} className="page-title">{currentPage.label}</Title>
          </Group>
          <Badge variant="light" color="statconvert" size="lg">
            1.0.0g5
          </Badge>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar className="sidebar">
        <Stack h="100%" gap={0}>
          <Box className="brand">
            <Box className="brand-mark" aria-hidden="true">
              SC
            </Box>
            <Box>
              <Text fw={800} size="lg" c="white">
                StatConvert
              </Text>
              <Text size="xs" c="blue.1">
                Statistical data, made portable
              </Text>
            </Box>
          </Box>
          <SidebarNavigation
            items={navigationItems}
            activePage={activePage}
            onSelect={selectPage}
          />
          <ApiStatus />
        </Stack>
      </AppShell.Navbar>

      <AppShell.Main className="workspace">
        {pageContent()}
      </AppShell.Main>
    </AppShell>
  );
}

export default App;
