/** First-load geometry: neutral bars, no spinner and no placeholder numbers. */
export function OverviewSkeleton() {
  return (
    <div className="overview-skeleton" aria-hidden="true" data-loading="true">
      <div className="skeleton skeleton-summary" />
      <div className="skeleton skeleton-heading" />
      <div className="skeleton skeleton-row" />
      <div className="skeleton skeleton-row" />
      <div className="skeleton skeleton-heading" />
      <div className="columns">
        <div>
          <div className="skeleton skeleton-heading" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
        </div>
        <div>
          <div className="skeleton skeleton-heading" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
          <div className="skeleton skeleton-row" />
        </div>
      </div>
    </div>
  );
}
