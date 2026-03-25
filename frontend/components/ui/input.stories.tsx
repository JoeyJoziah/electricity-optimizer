import type { Meta, StoryObj } from "@storybook/react";
import { Input } from "./input";

const meta = {
  title: "UI/Input",
  component: Input,
  tags: ["autodocs"],
  argTypes: {
    label: { control: "text" },
    placeholder: { control: "text" },
    error: { control: "text" },
    helperText: { control: "text" },
    success: { control: "boolean" },
    successText: { control: "text" },
    disabled: { control: "boolean" },
    type: {
      control: "select",
      options: ["text", "email", "password", "number", "tel", "url"],
    },
  },
} satisfies Meta<typeof Input>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    placeholder: "Enter your email",
  },
};

export const WithLabel: Story = {
  args: {
    label: "Email Address",
    placeholder: "you@example.com",
  },
};

export const WithLabelSuffix: Story = {
  args: {
    label: "ZIP Code",
    labelSuffix: "(optional)",
    placeholder: "10001",
  },
};

export const WithHelperText: Story = {
  args: {
    label: "API Key",
    placeholder: "sk_live_...",
    helperText: "Find your API key in the developer dashboard.",
  },
};

export const WithError: Story = {
  args: {
    label: "Email Address",
    placeholder: "you@example.com",
    defaultValue: "not-an-email",
    error: "Please enter a valid email address.",
  },
};

export const WithSuccess: Story = {
  args: {
    label: "Email Address",
    placeholder: "you@example.com",
    defaultValue: "user@rateshift.app",
    success: true,
    successText: "Email verified successfully.",
  },
};

export const Disabled: Story = {
  args: {
    label: "Region",
    defaultValue: "US-NY",
    disabled: true,
  },
};

export const PasswordInput: Story = {
  args: {
    label: "Password",
    type: "password",
    placeholder: "Enter your password",
  },
};

export const NumberInput: Story = {
  args: {
    label: "Monthly Budget ($)",
    type: "number",
    placeholder: "150",
    helperText: "Set your target monthly electricity budget.",
  },
};

export const AllStates: Story = {
  render: () => (
    <div className="max-w-sm space-y-6">
      <Input label="Default" placeholder="Type something..." />
      <Input
        label="With Helper"
        placeholder="Type something..."
        helperText="This is helper text."
      />
      <Input
        label="Error State"
        defaultValue="bad input"
        error="This field is required."
      />
      <Input
        label="Success State"
        defaultValue="valid@email.com"
        success
        successText="Looks good!"
      />
      <Input label="Disabled" defaultValue="Cannot edit" disabled />
    </div>
  ),
};
