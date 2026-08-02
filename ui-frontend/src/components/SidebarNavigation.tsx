import { Box, NavLink, ScrollArea } from "@mantine/core";

import type {
  NavigationItem,
  PageId,
} from "../routes/navigation";

interface SidebarNavigationProps {
  items: NavigationItem[];
  activePage: PageId;
  onSelect: (page: NavigationItem) => void;
}

export function SidebarNavigation({
  items,
  activePage,
  onSelect,
}: SidebarNavigationProps) {
  return (
    <ScrollArea className="navigation-scroll" type="auto">
      <Box p="md">
        {items.map((item) => {
          const Icon = item.icon;
          return (
          <NavLink
            key={item.id}
            active={activePage === item.id}
            label={item.label}
            leftSection={
              <span className="nav-icon" aria-hidden="true"><Icon size={18} stroke={1.8} /></span>
            }
            onClick={() => onSelect(item)}
            className="navigation-link"
            color="statconvert"
          />
          );
        })}
      </Box>
    </ScrollArea>
  );
}
