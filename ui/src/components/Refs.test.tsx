import { render, screen } from "@testing-library/react";
import { RefLink } from "./Refs";

describe("RefLink", () => {
  it("opens an external ref in a new tab with no referrer", () => {
    render(
      <RefLink
        ref={{
          type: "external",
          kind: "github_pr",
          key: "nurockplayer/eddington-1919#176",
          url: "https://github.com/nurockplayer/eddington-1919/pull/176",
        }}
      />,
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(link).toHaveTextContent("github_pr");
    expect(link).toHaveTextContent("nurockplayer/eddington-1919#176");
  });

  it("shows an unresolved record ref as not seen", () => {
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
    expect(screen.getByText("not seen")).toBeInTheDocument();
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
