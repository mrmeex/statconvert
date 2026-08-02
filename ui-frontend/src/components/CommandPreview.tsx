import {
  ActionIcon,
  Box,
  Collapse,
  CopyButton,
  Group,
  Paper,
  Text,
  Tooltip,
} from "@mantine/core";
import { IconCheck, IconChevronDown, IconChevronUp, IconCopy } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import { getJson } from "../lib/api";
import type { DataResponse, SettingsData } from "../lib/types";

interface CommandPreviewProps {
  command: string;
}

export function CommandPreview({ command }: CommandPreviewProps) {
  const [visible, setVisible] = useState<boolean | null>(null);
  const [opened, setOpened] = useState(true);

  useEffect(() => {
    void getJson<DataResponse<SettingsData>>("/api/settings")
      .then((response) => setVisible(response.data.settings.display.show_command_preview))
      .catch(() => setVisible(true));
  }, []);

  if (visible !== true) return null;

  return (
    <Paper withBorder radius="lg" className="command-panel">
      <Group justify="space-between" mb="xs">
        <Text className="eyebrow">Equivalent CLI command</Text>
        <Group gap="xs">
          <CopyButton value={command}>
            {({ copied, copy }) => (
              <Tooltip label={copied ? "Copied" : "Copy command"}>
                <ActionIcon variant="subtle" aria-label="Copy command" onClick={copy}>
                  {copied ? <IconCheck size={17} /> : <IconCopy size={17} />}
                </ActionIcon>
              </Tooltip>
            )}
          </CopyButton>
          <Tooltip label={opened ? "Collapse command" : "Show command"}>
            <ActionIcon variant="subtle" aria-label={opened ? "Collapse command" : "Show command"} onClick={() => setOpened((value) => !value)}>
              {opened ? <IconChevronUp size={17} /> : <IconChevronDown size={17} />}
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>
      <Collapse expanded={opened}>
        <Box component="code" className="command-code">
          {command || "Complete the required fields to preview the command."}
        </Box>
      </Collapse>
    </Paper>
  );
}
