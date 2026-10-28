export default function Card({ card, highlight }) {
  return (
    <article
      className={`card ${highlight ? "highlight" : ""}`}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData("text/plain", String(card.id));
        event.dataTransfer.effectAllowed = "move";
      }}
    >
      <div className="card-top">
        <strong>{card.display_name}</strong>
        {card.category ? <span className="tag">{card.category}</span> : null}
      </div>
      {card.subject ? <p className="subject">{card.subject}</p> : null}
      <dl>
        <div>
          <dt>Vendor</dt>
          <dd>{card.partner_id || "—"}</dd>
        </div>
        <div>
          <dt>Project</dt>
          <dd>{card.project_id || "—"}</dd>
        </div>
        <div>
          <dt>Package</dt>
          <dd>{card.package_id || "—"}</dd>
        </div>
      </dl>
    </article>
  );
}
