import { useEffect, useState } from "react";
import { Badge, Box, Group, Loader, Text } from "@mantine/core";

import { fetchShellStatus, type ShellStatus } from "../lib/api";

type ConnectionState =
  | { kind: "checking"; reconnecting: boolean }
  | { kind: "ready"; status: ShellStatus }
  | { kind: "error" };

export const HEALTH_POLL_INTERVAL_MS = 30_000;

export function ApiStatus() {
  const [state, setState] = useState<ConnectionState>({
    kind: "checking",
    reconnecting: false,
  });

  useEffect(() => {
    let active = true;
    let disconnected = false;
    let controller: AbortController | null = null;

    const check = async () => {
      controller?.abort();
      const requestController = new AbortController();
      controller = requestController;
      if (disconnected) {
        setState({ kind: "checking", reconnecting: true });
      }
      try {
        const status = await fetchShellStatus(requestController.signal);
        if (active) {
          disconnected = false;
          setState({ kind: "ready", status });
        }
      } catch {
        if (active && !requestController.signal.aborted) {
          disconnected = true;
          setState({ kind: "error" });
        }
      }
    };

    void check();
    const interval = window.setInterval(() => void check(), HEALTH_POLL_INTERVAL_MS);
    return () => {
      active = false;
      window.clearInterval(interval);
      controller?.abort();
    };
  }, []);

  return (
    <Box className="server-status">
      <Text size="xs" tt="uppercase" fw={700} c="blue.2" mb="xs">
        StatConvert backend
      </Text>
      {state.kind === "checking" && (
        <Group gap="xs">
          <Loader size="xs" color="blue.2" />
          <Text size="sm" c="gray.3">
            {state.reconnecting ? "Reconnecting…" : "Connecting…"}
          </Text>
        </Group>
      )}
      {state.kind === "error" && (
        <Box>
          <Badge color="red" variant="light">
            Disconnected
          </Badge>
          <Text size="xs" c="gray.4" mt={4}>
            Backend not reachable
          </Text>
        </Box>
      )}
      {state.kind === "ready" && (
        <>
          <Group gap="xs">
            <span className="status-dot" aria-hidden="true" />
            <Text size="sm" fw={600} c="white">
              Connected
            </Text>
          </Group>
          <Text size="xs" c="gray.4" mt={4}>
            StatConvert {state.status.version}
          </Text>
        </>
      )}
    </Box>
  );
}
