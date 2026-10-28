import { useState } from "react";
import Card from "./Card.jsx";

export default function Board({ columns, data, onDrop, highlightId, emptyNew }) {
  const [over, setOver] = useState(null);

  return (
    <div className="board">
      {columns.map((column) => {
        const cards = data[column.id] || [];
        const emptyText =
          column.id === "new" ? emptyNew || "Waiting for a purchase order from Odoo" : "Drop a PO here";
        return (
          <section
            key={column.id}
            className={`column ${over === column.id ? "over" : ""}`}
            onDragOver={(event) => {
              event.preventDefault();
              setOver(column.id);
            }}
            onDragLeave={() => setOver(null)}
            onDrop={(event) => {
              event.preventDefault();
              const cardId = Number(event.dataTransfer.getData("text/plain"));
              setOver(null);
              if (cardId) onDrop(cardId, column.id);
            }}
          >
            <header>
              <div>
                <h2>{column.title}</h2>
                <p>{column.hint}</p>
              </div>
              <span className="count">{cards.length}</span>
            </header>
            <div className="stack">
              {cards.length === 0 ? <p className="empty">{emptyText}</p> : null}
              {cards.map((card) => (
                <Card key={card.id} card={card} highlight={card.id === highlightId} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
