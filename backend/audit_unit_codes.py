"""Audit serial_numbers for junk unit codes. READ-ONLY — it deletes nothing.

Written while chasing reports of placeholder codes ("V1", stray strings) showing
up in the Stock Balance code lists. It checks the four shapes junk could take:

  1. serial_number that isn't the numeric system serial the generators produce
     (this is what a fabricated 'V1'/'V2' row would look like)
  2. rows carrying no asset_code and no consumable_code
  3. codes that don't match the generator format '<item_code>-1-<serial>'
  4. the same serial repeated within one item

It also reports, per item and batch, how much stock has codes and how much
doesn't — quantity received while an item's has_unit_code toggle was off carries
no code, which is expected, not corruption.

    python audit_unit_codes.py
"""
import asyncio

from sqlalchemy import text


async def main() -> None:
    from app.config import settings
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.connect() as c:
        total = (await c.execute(text("SELECT COUNT(*) FROM serial_numbers"))).scalar()
        print(f"serial_numbers rows: {total}")

        checks = [
            ("serial is not a plain numeric system serial (e.g. 'V1')", """
                SELECT sn.id, sn.serial_number, sn.asset_code, sn.consumable_code,
                       i.item_code, sn.batch_id, sn.status
                FROM serial_numbers sn LEFT JOIN items i ON i.id = sn.item_id
                WHERE sn.serial_number NOT REGEXP '^[0-9]+$' LIMIT 50"""),
            ("row carries no unit code at all", """
                SELECT sn.id, sn.serial_number, sn.asset_code, sn.consumable_code,
                       i.item_code, sn.batch_id, sn.status
                FROM serial_numbers sn LEFT JOIN items i ON i.id = sn.item_id
                WHERE sn.asset_code IS NULL AND sn.consumable_code IS NULL LIMIT 50"""),
            ("code does not match '<item_code>-1-<serial>'", """
                SELECT sn.id, sn.serial_number, sn.asset_code, sn.consumable_code,
                       i.item_code, sn.batch_id, sn.status
                FROM serial_numbers sn JOIN items i ON i.id = sn.item_id
                WHERE COALESCE(sn.asset_code, sn.consumable_code) IS NOT NULL
                  AND COALESCE(sn.asset_code, sn.consumable_code)
                      <> CONCAT(i.item_code, '-1-', sn.serial_number) LIMIT 50"""),
            ("duplicate serial within one item", """
                SELECT item_id, serial_number, COUNT(*) FROM serial_numbers
                GROUP BY item_id, serial_number HAVING COUNT(*) > 1 LIMIT 50"""),
        ]

        clean = True
        for label, sql in checks:
            rows = (await c.execute(text(sql))).fetchall()
            print(f"\n=== {label} === {len(rows)} found")
            if rows:
                clean = False
            for r in rows:
                print("   ", tuple(r))

        print("\n=== stock vs codes, per item and batch ===")
        rows = (await c.execute(text("""
            SELECT sb.item_id, i.item_code, i.name, i.has_unit_code,
                   sb.batch_id, b.batch_number, SUM(sb.available_qty) AS qty,
                   (SELECT COUNT(*) FROM serial_numbers sn
                     WHERE sn.item_id = sb.item_id AND sn.batch_id <=> sb.batch_id
                       AND sn.status = 'available') AS codes
            FROM stock_balance sb
            LEFT JOIN items i ON i.id = sb.item_id
            LEFT JOIN batches b ON b.id = sb.batch_id
            WHERE i.item_type IN ('asset', 'consumable')
            GROUP BY sb.item_id, i.item_code, i.name, i.has_unit_code, sb.batch_id, b.batch_number
            HAVING qty > 0
            ORDER BY sb.item_id, sb.batch_id
        """))).fetchall()
        for item_id, item_code, name, toggle, batch_id, batch_no, qty, codes in rows:
            gap = float(qty or 0) - float(codes or 0)
            flag = "" if gap <= 0 else f"  <-- {gap:g} unit(s) with no code"
            print(f"  item {item_id} [{item_code}] {name!r} toggle={toggle} "
                  f"batch={batch_id} {batch_no!r}: qty={qty} codes={codes}{flag}")

        print("\nNo junk rows found." if clean else "\nJunk rows found — review the lists above.")


if __name__ == "__main__":
    asyncio.run(main())
