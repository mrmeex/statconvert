import { useMemo, useState } from "react";
import {
  ActionIcon, Button, Group, Loader, Modal, ScrollArea, Stack, Table,
  Text, TextInput, Tooltip,
} from "@mantine/core";
import { IconArrowUp, IconFile, IconFolder, IconFolderOpen } from "@tabler/icons-react";

import { getJson, postJson } from "../lib/api";
import type { DataResponse, PathBrowseResponse, SettingsData } from "../lib/types";
import { ErrorAlert } from "./ErrorAlert";

interface PathPickerFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onCommit?: (value: string, generatedExtension?: boolean) => void;
  description?: string;
  placeholder?: string;
  selection?: "file" | "directory" | "save_file";
  extensions?: string[];
  required?: boolean;
  allowDirectorySelection?: boolean;
  allowSaveSelection?: boolean;
}

function parentPath(value: string): string {
  const trimmed = value.replace(/[\\/]+$/, "");
  const index = Math.max(trimmed.lastIndexOf("\\"), trimmed.lastIndexOf("/"));
  return index > 2 ? trimmed.slice(0, index) : trimmed;
}

function joinPath(directory: string, name: string): string {
  const separator = directory.includes("\\") ? "\\" : "/";
  return `${directory.replace(/[\\/]+$/, "")}${separator}${name}`;
}

export function PathPickerField({
  label, value, onChange, onCommit, description, placeholder, selection = "file",
  extensions = [], required, allowDirectorySelection = false, allowSaveSelection = false,
}: PathPickerFieldProps) {
  const [opened, setOpened] = useState(false);
  const [root, setRoot] = useState("");
  const [directory, setDirectory] = useState("");
  const [listing, setListing] = useState<PathBrowseResponse["data"] | null>(null);
  const [filename, setFilename] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [activeSelection, setActiveSelection] = useState(selection);
  const hint = useMemo(() => extensions.length ? extensions.join(", ") : "all files", [extensions]);

  const open = async (nextSelection = selection) => {
    setActiveSelection(nextSelection);
    let initial = parentPath(value);
    if (nextSelection === "directory" && value) {
      try {
        const inspected = await postJson<DataResponse<Record<string, unknown>>>("/api/files/inspect-path", { path: value });
        initial = inspected.data.is_directory === true ? value : parentPath(value);
      } catch {
        initial = value;
      }
    }
    try {
      const response = await getJson<DataResponse<SettingsData>>("/api/settings");
      const paths = response.data.settings.paths;
      if (!initial) {
        initial = paths.remember_last_paths
          ? nextSelection === "save_file"
            ? paths.last_output_directory
            : paths.last_input_directory
          : "";
        initial ||= paths.path_browser_start_directory || paths.default_working_directory;
      }
    } catch {
      // A picker remains usable with an explicitly entered path if preferences fail.
    }
    setRoot(initial);
    setDirectory(initial);
    setFilename(nextSelection === "save_file" ? value.slice(Math.max(value.lastIndexOf("\\"), value.lastIndexOf("/")) + 1) : "");
    setListing(null);
    setError(null);
    setOpened(true);
  };

  const browse = async (nextDirectory = directory || root) => {
    setLoading(true);
    setError(null);
    try {
      const response = await postJson<PathBrowseResponse>("/api/files/browse", {
        root_path: root,
        directory: nextDirectory,
        selection: activeSelection,
        extensions,
      });
      setDirectory(response.data.directory);
      setListing(response.data);
    } catch (nextError) {
      setError(nextError);
    } finally {
      setLoading(false);
    }
  };

  const choose = (path: string) => {
    const generatedExtension = activeSelection === "save_file" && extensions.length === 1 && !/\.[^\\/.]+$/.test(path);
    const chosen = generatedExtension
      ? `${path}${extensions[0]}`
      : path;
    if (onCommit) onCommit(chosen, generatedExtension);
    else onChange(chosen);
    void postJson<DataResponse<SettingsData>>("/api/settings/remember-path", {
      path: chosen,
      kind: activeSelection === "save_file" ? "output" : "input",
    }).catch(() => undefined);
    setOpened(false);
  };

  return (
    <>
      <TextInput
        label={label}
        description={description}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.currentTarget.value)}
        onBlur={() => onCommit?.(value)}
        required={required}
        rightSection={allowDirectorySelection ? (
          <Group gap={2} wrap="nowrap">
            <Tooltip label="Browse file">
              <ActionIcon variant="subtle" onClick={() => void open("file")} aria-label={`Browse file for ${label.toLowerCase()}`}>
                <IconFile size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Browse folder">
              <ActionIcon variant="subtle" onClick={() => void open("directory")} aria-label={`Browse folder for ${label.toLowerCase()}`}>
                <IconFolderOpen size={18} />
              </ActionIcon>
            </Tooltip>
          </Group>
        ) : allowSaveSelection ? (
          <Group gap={2} wrap="nowrap">
            <Tooltip label="Select existing file">
              <ActionIcon variant="subtle" onClick={() => void open("file")} aria-label={`Browse existing file for ${label.toLowerCase()}`}>
                <IconFile size={18} />
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Choose save path">
              <ActionIcon variant="subtle" onClick={() => void open("save_file")} aria-label={`Browse save path for ${label.toLowerCase()}`}>
                <IconFolderOpen size={18} />
              </ActionIcon>
            </Tooltip>
          </Group>
        ) : (
          <Tooltip label="Browse local paths">
            <ActionIcon variant="subtle" onClick={() => void open()} aria-label={`Browse for ${label.toLowerCase()}`}>
              <IconFolderOpen size={18} />
            </ActionIcon>
          </Tooltip>
        )}
        rightSectionWidth={allowDirectorySelection || allowSaveSelection ? 70 : undefined}
      />
      <Modal opened={opened} onClose={() => setOpened(false)} title={`Browse for ${label}`} size="xl">
        <Stack>
          <Text size="sm" c="dimmed">
            Enter and confirm a starting folder. Navigation is limited to that folder and its descendants; the browser never scans outside it.
          </Text>
          <Group align="end">
            <TextInput label="Confirmed starting folder" value={root} onChange={(event) => { setRoot(event.currentTarget.value); setDirectory(event.currentTarget.value); setListing(null); }} style={{ flex: 1 }} />
            <Button variant="light" onClick={() => void browse(root)} disabled={!root || loading} leftSection={loading ? <Loader size={14} /> : <IconFolderOpen size={16} />}>Open</Button>
          </Group>
          <ErrorAlert error={error} />
          {listing && (
            <>
              <Group justify="space-between">
                <Text size="sm" fw={600}>{listing.directory}</Text>
                {listing.parent && <Button size="xs" variant="subtle" leftSection={<IconArrowUp size={15} />} onClick={() => void browse(listing.parent!)}>Parent</Button>}
              </Group>
              <ScrollArea h={320}>
                <Table highlightOnHover>
                  <Table.Tbody>
                    {listing.entries.map((entry) => (
                      <Table.Tr key={entry.path} onDoubleClick={() => entry.is_directory ? void browse(entry.path) : choose(entry.path)}>
                        <Table.Td w={38}>{entry.is_directory ? <IconFolder size={18} /> : <IconFile size={18} />}</Table.Td>
                        <Table.Td>{entry.name}</Table.Td>
                        <Table.Td ta="right">
                          {entry.is_directory ? (
                            <Button size="xs" variant="subtle" onClick={() => void browse(entry.path)}>Open</Button>
                          ) : activeSelection !== "directory" ? (
                            <Button size="xs" variant="subtle" onClick={() => choose(entry.path)}>Select</Button>
                          ) : null}
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
              {listing.truncated && <Text size="xs" c="dimmed">Showing the first 1,000 entries.</Text>}
              {activeSelection === "directory" && <Button onClick={() => choose(listing.directory)}>Choose this folder</Button>}
              {activeSelection === "save_file" && (
                <Group align="end">
                  <TextInput label={`File name (${hint})`} value={filename} onChange={(event) => setFilename(event.currentTarget.value)} style={{ flex: 1 }} />
                  <Button onClick={() => choose(joinPath(listing.directory, filename))} disabled={!filename}>Choose output</Button>
                </Group>
              )}
            </>
          )}
        </Stack>
      </Modal>
    </>
  );
}
