import type { Meta, StoryObj } from "@storybook/react";
import {
  Skeleton,
  CardSkeleton,
  ChartSkeleton,
  TableRowSkeleton,
} from "./skeleton";

const meta = {
  title: "UI/Skeleton",
  component: Skeleton,
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["text", "circular", "rectangular"],
    },
    width: { control: "text" },
    height: { control: "text" },
  },
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

export const TextLine: Story = {
  args: {
    variant: "text",
    className: "w-64",
  },
};

export const Circular: Story = {
  args: {
    variant: "circular",
    width: 48,
    height: 48,
  },
};

export const Rectangular: Story = {
  args: {
    variant: "rectangular",
    width: "100%",
    height: 200,
  },
};

export const TextBlock: Story = {
  render: () => (
    <div className="max-w-sm space-y-2">
      <Skeleton variant="text" className="h-5 w-3/4" />
      <Skeleton variant="text" className="h-4 w-full" />
      <Skeleton variant="text" className="h-4 w-5/6" />
      <Skeleton variant="text" className="h-4 w-2/3" />
    </div>
  ),
};

export const ProfileSkeleton: Story = {
  render: () => (
    <div className="flex items-center gap-4">
      <Skeleton variant="circular" width={56} height={56} />
      <div className="space-y-2 flex-1">
        <Skeleton variant="text" className="h-5 w-1/3" />
        <Skeleton variant="text" className="h-4 w-1/2" />
      </div>
    </div>
  ),
};

export const CardSkeletonPreset: Story = {
  render: () => (
    <div className="max-w-sm">
      <CardSkeleton />
    </div>
  ),
};

export const ChartSkeletonPreset: Story = {
  render: () => (
    <div className="max-w-lg">
      <ChartSkeleton height={250} />
    </div>
  ),
};

export const TableSkeletonPreset: Story = {
  render: () => (
    <table className="w-full max-w-2xl">
      <tbody>
        <TableRowSkeleton columns={4} />
        <TableRowSkeleton columns={4} />
        <TableRowSkeleton columns={4} />
        <TableRowSkeleton columns={4} />
      </tbody>
    </table>
  ),
};

export const DashboardSkeleton: Story = {
  render: () => (
    <div className="space-y-6 max-w-2xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <Skeleton variant="text" className="h-8 w-48" />
        <Skeleton variant="rectangular" width={120} height={36} />
      </div>

      {/* Stat cards row */}
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            className="rounded-xl border border-gray-200 bg-white p-4"
          >
            <Skeleton variant="text" className="h-4 w-20 mb-2" />
            <Skeleton variant="text" className="h-8 w-28" />
          </div>
        ))}
      </div>

      {/* Chart */}
      <ChartSkeleton height={200} />

      {/* Table */}
      <div className="rounded-xl border border-gray-200 bg-white p-4">
        <Skeleton variant="text" className="h-6 w-32 mb-4" />
        <table className="w-full">
          <tbody>
            <TableRowSkeleton columns={5} />
            <TableRowSkeleton columns={5} />
            <TableRowSkeleton columns={5} />
          </tbody>
        </table>
      </div>
    </div>
  ),
};
