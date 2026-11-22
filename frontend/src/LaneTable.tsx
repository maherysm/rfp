import { Fragment, useState } from "react";
import { api, REQUIREMENTS, type Lane, type Rfp } from "./api";

type Props = { rfp: Rfp; run: (action: () => Promise<unknown>) => void };

export function LaneTable({ rfp, run }: Props) {
  const [openLaneId, setOpenLaneId] = useState<number | null>(null);
  const canEditRequirements = rfp.status === "review_plan";
  const canEditPrices = rfp.status === "review_prices";

  function toggleRequirement(lane: Lane, requirement: string) {
    const updated = lane.requirements.includes(requirement)
      ? lane.requirements.filter((r) => r !== requirement)
      : [...lane.requirements, requirement];
    run(() => api.setRequirements(lane.id, updated));
  }

  function savePrice(lane: Lane, value: string) {
    const price = Number(value);
    if (price > 0 && price !== lane.price) run(() => api.setPrice(lane.id, price));
  }

  return (
    <table className="lanes">
      <thead>
        <tr>
          <th>Lane</th>
          <th>Tons</th>
          <th>Requirements</th>
          <th>Route</th>
          <th>Days / max</th>
          <th>USD per ton</th>
          <th>Issues</th>
        </tr>
      </thead>
      <tbody>
        {rfp.lanes.map((lane) => (
          <Fragment key={lane.id}>
            <tr className={lane.issue ? "has-issue" : ""} onClick={() => setOpenLaneId(openLaneId === lane.id ? null : lane.id)}>
              <td>
                {lane.origin}-{lane.destination}
              </td>
              <td>{lane.tons}</td>
              <td>{lane.requirements.join(", ") || "none"}</td>
              <td>{lane.route.join(" > ") || "-"}</td>
              <td>
                {lane.transit_days ?? "-"} / {lane.max_days}
              </td>
              <td onClick={(e) => e.stopPropagation()}>
                {canEditPrices && lane.route.length > 0 ? (
                  <input
                    type="number"
                    defaultValue={lane.price ?? ""}
                    placeholder="missing"
                    onBlur={(e) => savePrice(lane, e.target.value)}
                  />
                ) : (
                  (lane.price?.toLocaleString() ?? "")
                )}
              </td>
              <td className="issue">{lane.issue}</td>
            </tr>
            {openLaneId === lane.id && (
              <tr className="details">
                <td colSpan={7}>
                  <p>
                    <strong>Shipper email:</strong> {lane.email}
                  </p>
                  {lane.alternative && (
                    <p>
                      <strong>Other route option:</strong> {lane.alternative.route.join(" > ")},{" "}
                      {lane.alternative.transit_days} days (max {lane.max_days})
                      {lane.alternative.unmet.length > 0
                        ? `, not available: ${lane.alternative.unmet.join(", ")}`
                        : ", meets every requirement"}{" "}
                      {canEditRequirements && (
                        <button onClick={() => run(() => api.chooseRoute(lane.id, lane.alternative!.route))}>
                          Use this route
                        </button>
                      )}
                    </p>
                  )}
                  {canEditRequirements && (
                    <p>
                      <strong>Edit requirements:</strong>{" "}
                      {REQUIREMENTS.map((requirement) => (
                        <label key={requirement}>
                          <input
                            type="checkbox"
                            checked={lane.requirements.includes(requirement)}
                            onChange={() => toggleRequirement(lane, requirement)}
                          />
                          {requirement}
                        </label>
                      ))}
                    </p>
                  )}
                </td>
              </tr>
            )}
          </Fragment>
        ))}
      </tbody>
    </table>
  );
}
