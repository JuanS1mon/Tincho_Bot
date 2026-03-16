import { NextRequest, NextResponse } from "next/server";

export async function GET(req: NextRequest) {
  try {
    const res = await fetch(process.env.BACKEND_URL + "/market-analysis", { cache: "no-store" });
    if (!res.ok) return NextResponse.json({ error: "No se pudo obtener análisis de mercado" }, { status: res.status });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: "Error de conexión con backend" }, { status: 500 });
  }
}
