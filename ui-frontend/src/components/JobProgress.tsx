import { useEffect, useState } from "react";
import {
  Badge,
  Button,
  Group,
  Paper,
  Progress,
  Stack,
  Text,
} from "@mantine/core";
import { IconBan } from "@tabler/icons-react";

import { cancelJob, getJob } from "../lib/api";
import { jobStatusColor } from "../lib/status";
import type { JobSnapshot } from "../lib/types";
import { ErrorAlert } from "./ErrorAlert";
import { BatchProgressTable } from "./BatchProgressTable";
import { CompareResultView } from "./CompareResultView";
import { WorkflowResultView } from "./WorkflowResultView";

interface JobProgressProps {
  jobId: string | null;
  onComplete?: (job: JobSnapshot) => void;
  onUpdate?: (job: JobSnapshot) => void;
}

const terminalStatuses = new Set(["succeeded", "failed", "cancelled"]);

export function JobProgress({ jobId, onComplete, onUpdate }: JobProgressProps) {
  const [job, setJob] = useState<JobSnapshot | null>(null);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    let active = true;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await getJob(jobId);
        if (!active) return;
        setJob(next);
        onUpdate?.(next);
        setError(null);
        if (terminalStatuses.has(next.status)) {
          onComplete?.(next);
          return;
        }
        timer = window.setTimeout(poll, 400);
      } catch (nextError) {
        if (active) setError(nextError);
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [jobId, onComplete, onUpdate]);

  if (!jobId) {
    return null;
  }
  return (
    <Stack gap="md">
      <ErrorAlert error={error} />
      <Paper withBorder radius="lg" p="lg">
        <Group justify="space-between" mb="sm">
          <Text fw={700}>{job?.workflow === "batch" ? "Batch progress" : "Background job"}</Text>
          <Badge color={jobStatusColor(job?.status ?? "connecting")} variant="light">
            {job?.status ?? "connecting"}
          </Badge>
        </Group>
        <Progress value={(job?.progress ?? 0) * 100} animated size="lg" />
        {job?.events.at(-1)?.message && (
          <Text size="sm" c="dimmed" mt="sm">
            {job.events.at(-1)?.message}
          </Text>
        )}
        {job && !terminalStatuses.has(job.status) && (
          <Button
            variant="subtle"
            color="red"
            mt="sm"
            leftSection={<IconBan size={16} />}
            onClick={() => void cancelJob(jobId).then(setJob).catch(setError)}
          >
            Request cancellation
          </Button>
        )}
        {job?.workflow === "batch" && <BatchProgressTable events={job.events} />}
      </Paper>
      {job?.error && <ErrorAlert error={new Error(job.error.message)} />}
      {job?.result && (job.workflow === "compare"
        ? <CompareResultView data={job.result} />
        : <WorkflowResultView workflow={job.workflow} data={job.result} />)}
    </Stack>
  );
}
