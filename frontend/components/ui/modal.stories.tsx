import React, { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";
import { fn } from "storybook/test";
import { Modal } from "./modal";
import { Button } from "./button";

const meta = {
  title: "UI/Modal",
  component: Modal,
  tags: ["autodocs"],
  argTypes: {
    open: { control: "boolean" },
    variant: {
      control: "select",
      options: ["default", "danger"],
    },
    title: { control: "text" },
    description: { control: "text" },
    confirmLabel: { control: "text" },
    cancelLabel: { control: "text" },
  },
  args: {
    onClose: fn(),
    onConfirm: fn(),
  },
  // Render modals into a portal-friendly container
  decorators: [
    (Story) => (
      <div style={{ minHeight: "400px" }}>
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof Modal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    open: true,
    title: "Confirm Action",
    description: "Are you sure you want to proceed with this action?",
    confirmLabel: "Confirm",
    cancelLabel: "Cancel",
  },
};

export const DangerVariant: Story = {
  args: {
    open: true,
    title: "Delete Connection",
    description:
      "This will permanently delete the connection and all associated data. This action cannot be undone.",
    confirmLabel: "Delete",
    cancelLabel: "Keep",
    variant: "danger",
  },
};

export const WithCustomContent: Story = {
  args: {
    open: true,
    title: "Set Price Alert",
    description: "Get notified when rates drop below your threshold.",
  },
  render: (args) => (
    <Modal {...args}>
      <div className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Price Threshold (cents/kWh)
          </label>
          <input
            type="number"
            className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm"
            placeholder="12.5"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Region
          </label>
          <select className="w-full rounded-lg border border-gray-300 px-4 py-2.5 text-sm">
            <option>US-NY (New York)</option>
            <option>US-CA (California)</option>
            <option>US-TX (Texas)</option>
          </select>
        </div>
      </div>
    </Modal>
  ),
};

export const InformationalOnly: Story = {
  args: {
    open: true,
    title: "Rate Update",
    description:
      "Electricity rates in your region have changed. Your new rate is $0.182/kWh, down from $0.193/kWh. This represents a 5.7% decrease.",
  },
};

export const Interactive: Story = {
  args: {
    open: false,
    title: "Switch Rate Plan",
  },
  render: () => {
    const InteractiveModal = () => {
      const [open, setOpen] = useState(false);

      return (
        <div>
          <Button onClick={() => setOpen(true)}>Open Modal</Button>
          <Modal
            open={open}
            onClose={() => setOpen(false)}
            onConfirm={() => setOpen(false)}
            title="Switch Rate Plan"
            description="Switch to the Time-of-Use plan to save an estimated $23/month based on your usage patterns."
            confirmLabel="Switch Plan"
            cancelLabel="Not Now"
          />
        </div>
      );
    };

    return <InteractiveModal />;
  },
};

export const InteractiveDanger: Story = {
  args: {
    open: false,
    title: "Delete Account",
    variant: "danger",
  },
  render: () => {
    const InteractiveDangerModal = () => {
      const [open, setOpen] = useState(false);

      return (
        <div>
          <Button variant="danger" onClick={() => setOpen(true)}>
            Delete Account
          </Button>
          <Modal
            open={open}
            onClose={() => setOpen(false)}
            onConfirm={() => setOpen(false)}
            title="Delete Account"
            description="This will permanently delete your account, all connections, alerts, and usage history. This action cannot be undone."
            confirmLabel="Delete Everything"
            cancelLabel="Cancel"
            variant="danger"
          />
        </div>
      );
    };

    return <InteractiveDangerModal />;
  },
};
