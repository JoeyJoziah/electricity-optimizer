import type { Meta, StoryObj } from "@storybook/react";
import { Badge } from "./badge";

const meta = {
  title: "UI/Badge",
  component: Badge,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "success", "warning", "danger", "info"],
    },
    size: {
      control: "select",
      options: ["sm", "md"],
    },
  },
} satisfies Meta<typeof Badge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    children: "Default",
    variant: "default",
  },
};

export const Success: Story = {
  args: {
    children: "Active",
    variant: "success",
  },
};

export const Warning: Story = {
  args: {
    children: "Pending",
    variant: "warning",
  },
};

export const Danger: Story = {
  args: {
    children: "Expired",
    variant: "danger",
  },
};

export const Info: Story = {
  args: {
    children: "New",
    variant: "info",
  },
};

export const Small: Story = {
  args: {
    children: "SM",
    size: "sm",
    variant: "info",
  },
};

export const MediumSize: Story = {
  args: {
    children: "Medium",
    size: "md",
    variant: "info",
  },
};

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3">
      <Badge variant="default">Default</Badge>
      <Badge variant="success">Active</Badge>
      <Badge variant="warning">Pending</Badge>
      <Badge variant="danger">Expired</Badge>
      <Badge variant="info">New</Badge>
    </div>
  ),
};

export const AllSizes: Story = {
  render: () => (
    <div className="flex items-center gap-3">
      <Badge variant="info" size="sm">
        Small
      </Badge>
      <Badge variant="info" size="md">
        Medium
      </Badge>
    </div>
  ),
};

export const RealWorldUsage: Story = {
  render: () => (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">
          Connection Status:
        </span>
        <Badge variant="success">Connected</Badge>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Plan:</span>
        <Badge variant="info">Pro</Badge>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Rate Trend:</span>
        <Badge variant="warning">Increasing</Badge>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-700">Alert:</span>
        <Badge variant="danger">Price Spike</Badge>
      </div>
    </div>
  ),
};
