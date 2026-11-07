import { render, screen } from "@testing-library/react";
import { RefLink } from "./Refs";

describe("RefLink", () => {
  it("opens an external ref in a new tab with no referrer", () => {
    render(
      <RefLink
        ref={{
          type: "external",
          kind: "github_pr",
          key: "example/repo#176",
          url: "https://example.invalid/example/repo/pull/176",
        }}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByText("github_pr")).toBeInTheDocument();
    expect(screen.getByText("example/repo#176")).toBeInTheDocument();
  });

  it("shows an unresolved record ref as not found", () => {
    render(
      <RefLink
        ref={{
          type: "run",
          id: "old-worker-88-retry",
          source_id: "tachiko-harness@mbp",
          resolved: false,
        }}
      />,
    );
    expect(screen.getByText("not found")).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("old-worker-88-retry")).toBeInTheDocument();
  });

  it("links a resolved record ref to the detail route", () => {
    render(
      <RefLink
        ref={{
          type: "run",
          id: "old-worker-88",
          source_id: "tachiko-harness@mbp",
          resolved: true,
        }}
      />,
    );
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe(
      "/run?source_id=tachiko-harness%40mbp&type=run&id=old-worker-88",
    );
  });
});
