import React from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "storybook/test";
import { Toast } from "./toast";

const meta = {
  title: "UI/Toast",
  component: Toast,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["success", "error", "warning", "info"],
    },
    title: { control: "text" },
    description: { control: "text" },
  },
  args: {
    onDismiss: fn(),
  },
  decorators: [
    (Story) => (
      <div className="max-w-sm">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Toast>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Success: Story = {
  args: {
    id: "1",
    variant: "success",
    title: "Connection Added",
    description: "Your utility account has been linked successfully.",
  },
};

export const Error: Story = {
  args: {
    id: "2",
    variant: "error",
    title: "Sync Failed",
    description: "Unable to fetch latest rates. Please try again.",
  },
};

export const Warning: Story = {
  args: {
    id: "3",
    variant: "warning",
    title: "Rate Increase Detected",
    description: "Your electricity rate increased by 8% this billing period.",
  },
};

export const Info: Story = {
  args: {
    id: "4",
    variant: "info",
    title: "New Feature Available",
    description: "Time-of-Use optimization is now available for your region.",
  },
};

export const TitleOnly: Story = {
  args: {
    id: "5",
    variant: "success",
    title: "Settings saved.",
  },
};

export const LongDescription: Story = {
  args: {
    id: "6",
    variant: "info",
    title: "Forecast Updated",
    description:
      "The ML model has generated new price forecasts for your region based on the latest weather data, historical patterns, and market conditions. Check the dashboard for details.",
  },
};

export const AllVariants: Story = {
  args: {
    id: "all",
    variant: "info",
    title: "All Variants",
  },
  render: () => (
    <div className="space-y-3 max-w-sm">
      <Toast
        id="s1"
        variant="success"
        title="Connection Added"
        description="Your utility account has been linked successfully."
        onDismiss={fn()}
      />
      <Toast
        id="e1"
        variant="error"
        title="Sync Failed"
        description="Unable to fetch latest rates. Please try again."
        onDismiss={fn()}
      />
      <Toast
        id="w1"
        variant="warning"
        title="Rate Increase Detected"
        description="Your electricity rate increased by 8% this billing period."
        onDismiss={fn()}
      />
      <Toast
        id="i1"
        variant="info"
        title="New Feature Available"
        description="Time-of-Use optimization is now available for your region."
        onDismiss={fn()}
      />
    </div>
  ),
};
