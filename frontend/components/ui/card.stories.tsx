import type { Meta, StoryObj } from "@storybook/react";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "./card";
import { Button } from "./button";

const meta = {
  title: "UI/Card",
  component: Card,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "bordered", "elevated"],
    },
    padding: {
      control: "select",
      options: ["none", "sm", "md", "lg"],
    },
  },
} satisfies Meta<typeof Card>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    variant: "default",
    children: "A simple default card with some content inside.",
  },
};

export const Bordered: Story = {
  args: {
    variant: "bordered",
    children: "A bordered card with a visible border.",
  },
};

export const Elevated: Story = {
  args: {
    variant: "elevated",
    children: "An elevated card with a shadow.",
  },
};

export const NoPadding: Story = {
  args: {
    variant: "bordered",
    padding: "none",
    children: (
      <div className="p-4">
        Content with custom padding inside a no-padding card.
      </div>
    ),
  },
};

export const SmallPadding: Story = {
  args: {
    variant: "bordered",
    padding: "sm",
    children: "Card with small padding.",
  },
};

export const LargePadding: Story = {
  args: {
    variant: "bordered",
    padding: "lg",
    children: "Card with large padding.",
  },
};

export const FullComposition: Story = {
  render: () => (
    <Card variant="bordered" padding="lg">
      <CardHeader>
        <CardTitle>Electricity Usage</CardTitle>
      </CardHeader>
      <CardDescription>
        Overview of your electricity consumption for the current billing period.
      </CardDescription>
      <CardContent>
        <div className="space-y-2 mt-2">
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Average Daily Usage</span>
            <span className="font-medium">24.5 kWh</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Estimated Monthly Cost</span>
            <span className="font-medium">$142.30</span>
          </div>
          <div className="flex justify-between text-sm">
            <span className="text-gray-600">Current Rate</span>
            <span className="font-medium">$0.193/kWh</span>
          </div>
        </div>
      </CardContent>
      <CardFooter>
        <Button variant="outline" size="sm">
          View Details
        </Button>
        <Button variant="primary" size="sm">
          Optimize
        </Button>
      </CardFooter>
    </Card>
  ),
};

export const HeaderWithAction: Story = {
  render: () => (
    <Card variant="bordered">
      <CardHeader>
        <CardTitle>Rate Plans</CardTitle>
        <Button variant="ghost" size="sm">
          Refresh
        </Button>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-gray-600">
          Compare available rate plans for your region.
        </p>
      </CardContent>
    </Card>
  ),
};

export const AllVariants: Story = {
  render: () => (
    <div className="space-y-4">
      <Card variant="default">
        <CardTitle>Default Variant</CardTitle>
        <p className="mt-2 text-sm text-gray-600">
          No border, just background.
        </p>
      </Card>
      <Card variant="bordered">
        <CardTitle>Bordered Variant</CardTitle>
        <p className="mt-2 text-sm text-gray-600">With a subtle border.</p>
      </Card>
      <Card variant="elevated">
        <CardTitle>Elevated Variant</CardTitle>
        <p className="mt-2 text-sm text-gray-600">With a drop shadow.</p>
      </Card>
    </div>
  ),
};
