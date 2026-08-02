import { Alert, Text } from "@mantine/core";

import { ApiError } from "../lib/api";

interface ErrorAlertProps {
  error: unknown;
}

export function ErrorAlert({ error }: ErrorAlertProps) {
  if (!error) {
    return null;
  }
  const message = error instanceof Error ? error.message : String(error);
  const suggestion = error instanceof ApiError ? error.suggestion : null;
  return (
    <Alert color="red" title="StatConvert could not complete this request">
      <Text size="sm">{message}</Text>
      {suggestion && (
        <Text size="sm" mt="xs" fw={600}>
          {suggestion}
        </Text>
      )}
    </Alert>
  );
}
