import { render, screen } from "@testing-library/react";
import { Attention } from "./Attention";
import { snapshot } from "../test-fixtures";

describe("Attention", () => {
  it("renders the attention entries in the API's order", () => {
    const { container } = render(<Attention snapshot={snapshot} />);
    const rows = Array.from(container.querySelectorAll(".attention-row"));
    expect(rows.map((row) => row.getAttribute("data-reason"))).toEqual(
      snapshot.attention.map((entry) => entry.reason),
    );
  });

  it("says who must act and links each subject", () => {
    render(<Attention snapshot={snapshot} />);
    expect(screen.getAllByText("edd-lead").length).toBeGreaterThan(0);
    expect(screen.getAllByText("gteki-ops").length).toBeGreaterThan(0);
    expect(screen.getByText("unassigned")).toBeInTheDocument();
    expect(screen.getByText("eps-runner-19")).toBeInTheDocument();
    expect(screen.getByText("job-run-eps-77")).toBeInTheDocument();
  });

  it("shows source problems even when they have no subject", () => {
    render(<Attention snapshot={snapshot} />);
    expect(
      screen.getByText(/discontinuity: segment 0000000002 was replaced/),
    ).toBeInTheDocument();
    expect(screen.getByText("fleetglint@ci")).toBeInTheDocument();
  });
});
