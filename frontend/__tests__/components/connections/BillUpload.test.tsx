import { render, screen, fireEvent } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

import { BillUploadDropZone } from "@/components/connections/BillUploadDropZone";
import { BillUploadFilePreview } from "@/components/connections/BillUploadFilePreview";
import {
  BillUploadProgressBar,
  BillUploadProcessingStatus,
} from "@/components/connections/BillUploadProgress";
import {
  BillUploadSuccess,
  BillUploadFailure,
} from "@/components/connections/BillUploadResults";

// ---------------------------------------------------------------------------
// BillUploadDropZone
// ---------------------------------------------------------------------------

describe("BillUploadDropZone", () => {
  const handlers = {
    onDrop: jest.fn(),
    onDragOver: jest.fn(),
    onDragLeave: jest.fn(),
    onInputChange: jest.fn(),
  };

  beforeEach(() => {
    Object.values(handlers).forEach((fn) => fn.mockReset());
  });

  it("renders aria-label Upload a bill file", () => {
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    expect(
      screen.getByRole("button", { name: /upload a bill file/i }),
    ).toBeInTheDocument();
  });

  it("shows 'Drag and drop your bill here' when dragActive=false", () => {
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    expect(
      screen.getByText("Drag and drop your bill here"),
    ).toBeInTheDocument();
  });

  it("shows 'Drop file here' when dragActive=true", () => {
    render(
      <BillUploadDropZone
        dragActive={true}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    expect(screen.getByText("Drop file here")).toBeInTheDocument();
  });

  it("renders PDF/PNG/JPG badges", () => {
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    expect(screen.getByText("PDF")).toBeInTheDocument();
    expect(screen.getByText("PNG")).toBeInTheDocument();
    expect(screen.getByText("JPG")).toBeInTheDocument();
  });

  it("renders max file size note", () => {
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    expect(screen.getByText(/max file size/i)).toBeInTheDocument();
  });

  it("triggers click on hidden file input when button is clicked", () => {
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    const hiddenInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const clickSpy = jest
      .spyOn(hiddenInput, "click")
      .mockImplementation(() => {});
    fireEvent.click(
      screen.getByRole("button", { name: /upload a bill file/i }),
    );
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
  });

  it("triggers click on Enter key", () => {
    const ref = React.createRef<HTMLInputElement>();
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={ref}
        {...handlers}
      />,
    );
    const hiddenInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const clickSpy = jest
      .spyOn(hiddenInput, "click")
      .mockImplementation(() => {});
    fireEvent.keyDown(
      screen.getByRole("button", { name: /upload a bill file/i }),
      { key: "Enter" },
    );
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
  });

  it("triggers click on Space key", () => {
    const ref = React.createRef<HTMLInputElement>();
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={ref}
        {...handlers}
      />,
    );
    const hiddenInput = document.querySelector(
      'input[type="file"]',
    ) as HTMLInputElement;
    const clickSpy = jest
      .spyOn(hiddenInput, "click")
      .mockImplementation(() => {});
    fireEvent.keyDown(
      screen.getByRole("button", { name: /upload a bill file/i }),
      { key: " " },
    );
    expect(clickSpy).toHaveBeenCalledTimes(1);
    clickSpy.mockRestore();
  });

  it("calls onDrop handler on drop event", () => {
    render(
      <BillUploadDropZone
        dragActive={false}
        fileInputRef={React.createRef()}
        {...handlers}
      />,
    );
    fireEvent.drop(screen.getByRole("button", { name: /upload a bill file/i }));
    expect(handlers.onDrop).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// BillUploadFilePreview
// ---------------------------------------------------------------------------

describe("BillUploadFilePreview", () => {
  function makeFile(name: string, size: number, type: string): File {
    return new File(["x".repeat(size)], name, { type });
  }

  it("renders file name", () => {
    const file = makeFile("electricity-bill.pdf", 512000, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={false}
        isProcessing={false}
        onClear={jest.fn()}
      />,
    );
    expect(screen.getByText("electricity-bill.pdf")).toBeInTheDocument();
  });

  it("renders formatted file size in KB", () => {
    const file = makeFile("bill.pdf", 512000, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={false}
        isProcessing={false}
        onClear={jest.fn()}
      />,
    );
    expect(screen.getByText(/500\.0 KB/)).toBeInTheDocument();
  });

  it("renders 'PDF' label for application/pdf type", () => {
    const file = makeFile("invoice.png", 1024, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={false}
        isProcessing={false}
        onClear={jest.fn()}
      />,
    );
    // file.type is application/pdf so label should be "PDF"
    expect(screen.getByText(/PDF/)).toBeInTheDocument();
  });

  it("shows remove button when not uploading and not processing", () => {
    const file = makeFile("bill.pdf", 1024, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={false}
        isProcessing={false}
        onClear={jest.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /remove selected file/i }),
    ).toBeInTheDocument();
  });

  it("hides remove button when uploading=true", () => {
    const file = makeFile("bill.pdf", 1024, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={true}
        isProcessing={false}
        onClear={jest.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /remove selected file/i }),
    ).not.toBeInTheDocument();
  });

  it("hides remove button when isProcessing=true", () => {
    const file = makeFile("bill.pdf", 1024, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={false}
        isProcessing={true}
        onClear={jest.fn()}
      />,
    );
    expect(
      screen.queryByRole("button", { name: /remove selected file/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onClear when remove button is clicked", () => {
    const onClear = jest.fn();
    const file = makeFile("bill.pdf", 1024, "application/pdf");
    render(
      <BillUploadFilePreview
        file={file}
        uploading={false}
        isProcessing={false}
        onClear={onClear}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /remove selected file/i }),
    );
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

// ---------------------------------------------------------------------------
// BillUploadProgressBar
// ---------------------------------------------------------------------------

describe("BillUploadProgressBar", () => {
  it("renders null when uploading=false and progress=0", () => {
    const { container } = render(
      <BillUploadProgressBar uploading={false} uploadProgress={0} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders null when uploading=false and progress=100", () => {
    const { container } = render(
      <BillUploadProgressBar uploading={false} uploadProgress={100} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders progress bar when uploading=true", () => {
    render(<BillUploadProgressBar uploading={true} uploadProgress={42} />);
    expect(screen.getByText("Uploading...")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("renders progressbar role with correct aria-valuenow", () => {
    render(<BillUploadProgressBar uploading={true} uploadProgress={65} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "65");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("renders progress bar when uploading=false but progress is between 0-100", () => {
    render(<BillUploadProgressBar uploading={false} uploadProgress={50} />);
    expect(screen.getByText("50%")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BillUploadProcessingStatus
// ---------------------------------------------------------------------------

describe("BillUploadProcessingStatus", () => {
  it("shows 'Queued for processing...' when status=pending", () => {
    render(
      <BillUploadProcessingStatus
        parseResult={{
          status: "pending",
          extracted_data: null,
          error_message: null,
        }}
        pollCount={0}
      />,
    );
    expect(screen.getByText("Queued for processing...")).toBeInTheDocument();
  });

  it("shows 'Analyzing your bill...' when status=processing", () => {
    render(
      <BillUploadProcessingStatus
        parseResult={{
          status: "processing",
          extracted_data: null,
          error_message: null,
        }}
        pollCount={0}
      />,
    );
    expect(screen.getByText("Analyzing your bill...")).toBeInTheDocument();
  });

  it("shows 'Still working on it...' when pollCount > 10", () => {
    render(
      <BillUploadProcessingStatus
        parseResult={{
          status: "processing",
          extracted_data: null,
          error_message: null,
        }}
        pollCount={11}
      />,
    );
    expect(screen.getByText(/still working on it/i)).toBeInTheDocument();
  });

  it("omits 'Still working' message when pollCount <= 10", () => {
    render(
      <BillUploadProcessingStatus
        parseResult={{
          status: "processing",
          extracted_data: null,
          error_message: null,
        }}
        pollCount={5}
      />,
    );
    expect(screen.queryByText(/still working on it/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BillUploadSuccess
// ---------------------------------------------------------------------------

const _extracted = {
  rate_per_kwh: 0.145,
  supplier_name: "GreenPower CT",
  period_start: "2026-04-01",
  period_end: "2026-04-30",
  usage_kwh: 850,
  amount: 123.25,
  currency: "USD",
};

describe("BillUploadSuccess", () => {
  it("shows 'Bill processed successfully' banner", () => {
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("Bill processed successfully")).toBeInTheDocument();
  });

  it("renders rate in c/kWh when rate_per_kwh is set", () => {
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("14.50 c/kWh")).toBeInTheDocument();
  });

  it("renders supplier name when set", () => {
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("GreenPower CT")).toBeInTheDocument();
  });

  it("renders usage in kWh", () => {
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("850 kWh")).toBeInTheDocument();
  });

  it("renders formatted amount", () => {
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("$123.25")).toBeInTheDocument();
  });

  it("calls onComplete when Done is clicked", () => {
    const onComplete = jest.fn();
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={onComplete}
        onClearFile={jest.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /done/i }));
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it("calls onClearFile when Upload Another is clicked", () => {
    const onClearFile = jest.fn();
    render(
      <BillUploadSuccess
        extractedData={_extracted}
        onComplete={jest.fn()}
        onClearFile={onClearFile}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /upload another/i }));
    expect(onClearFile).toHaveBeenCalledTimes(1);
  });

  it("omits rate field when rate_per_kwh is null", () => {
    render(
      <BillUploadSuccess
        extractedData={{ ..._extracted, rate_per_kwh: null }}
        onComplete={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.queryByText(/c\/kWh/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// BillUploadFailure
// ---------------------------------------------------------------------------

describe("BillUploadFailure", () => {
  it("shows 'Failed to process bill' heading", () => {
    render(
      <BillUploadFailure
        errorMessage="File too blurry"
        onRetry={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("Failed to process bill")).toBeInTheDocument();
  });

  it("shows custom error message when provided", () => {
    render(
      <BillUploadFailure
        errorMessage="File too blurry"
        onRetry={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText("File too blurry")).toBeInTheDocument();
  });

  it("shows default message when errorMessage is null", () => {
    render(
      <BillUploadFailure
        errorMessage={null}
        onRetry={jest.fn()}
        onClearFile={jest.fn()}
      />,
    );
    expect(screen.getByText(/could not extract data/i)).toBeInTheDocument();
  });

  it("calls onRetry when Retry Upload is clicked", () => {
    const onRetry = jest.fn();
    render(
      <BillUploadFailure
        errorMessage={null}
        onRetry={onRetry}
        onClearFile={jest.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /retry upload/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("calls onClearFile when Choose Different File is clicked", () => {
    const onClearFile = jest.fn();
    render(
      <BillUploadFailure
        errorMessage={null}
        onRetry={jest.fn()}
        onClearFile={onClearFile}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /choose different file/i }),
    );
    expect(onClearFile).toHaveBeenCalledTimes(1);
  });
});
