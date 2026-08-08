import type { ComponentType } from "react";
import {
  IconArrowsDiff, IconArrowsExchange, IconBook2,
  IconFileAnalytics, IconFileSettings, IconHome, IconInfoCircle,
  IconPackages, IconSearch, IconSettings, IconShieldCheck, IconStack2,
  IconTransform,
} from "@tabler/icons-react";

export type PageId = "home" | "inspect" | "convert" | "batch" | "validate" |
  "transform" | "compare" | "report" | "collect" | "configs" | "reference" |
  "settings" | "about";

export type NavigationIcon = ComponentType<{ size?: number; stroke?: number; className?: string }>;

export interface NavigationItem {
  id: PageId;
  label: string;
  description: string;
  icon: NavigationIcon;
}

export const navigationItems: NavigationItem[] = [
  { id: "home", label: "Home", description: "Choose a StatConvert workflow and review the local UI status.", icon: IconHome },
  { id: "inspect", label: "Inspect", description: "Preview datasets, schema, labels, metadata, and profiles.", icon: IconSearch },
  { id: "convert", label: "Convert", description: "Configure a safe single-dataset conversion.", icon: IconArrowsExchange },
  { id: "batch", label: "Batch Convert", description: "Plan and follow conversions for a folder of datasets.", icon: IconStack2 },
  { id: "validate", label: "Validate", description: "Check dataset quality, contracts, and target readiness.", icon: IconShieldCheck },
  { id: "transform", label: "Transform", description: "Build ordered transform recipes with safe expressions.", icon: IconTransform },
  { id: "compare", label: "Compare", description: "Compare structure, metadata, and values between datasets.", icon: IconArrowsDiff },
  { id: "report", label: "Report", description: "Configure and generate a bounded dataset report.", icon: IconFileAnalytics },
  { id: "collect", label: "Collect", description: "Plan a manifest-driven multi-object workbook.", icon: IconPackages },
  { id: "configs", label: "Configs", description: "Create, validate, load, run, and export TOML workflows.", icon: IconFileSettings },
  { id: "reference", label: "Reference", description: "Browse formats, backends, and capabilities.", icon: IconBook2 },
  { id: "settings", label: "Settings", description: "Manage local paths, display defaults, and command logging.", icon: IconSettings },
  { id: "about", label: "About", description: "Review version, dependencies, runtime details, and local privacy.", icon: IconInfoCircle },
];
