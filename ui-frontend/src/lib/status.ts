export function jobStatusColor(status: string | null | undefined): string {
  switch ((status ?? "").toLowerCase()) {
    case "running":
      return "blue";
    case "succeeded":
    case "success":
    case "done":
      return "green";
    case "failed":
    case "error":
      return "red";
    case "cancelled":
    case "canceling":
    case "cancelling":
      return "orange";
    case "queued":
    case "connecting":
    default:
      return "gray";
  }
}
