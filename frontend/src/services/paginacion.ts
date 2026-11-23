import { apiFetch } from "./api";

/** Carga un catálogo completo; un fallo nunca se presenta como una lista completa vacía. */
export async function listarTodasLasPaginas<T>(path: string, params: Record<string, string | number | undefined> = {}, signal?: AbortSignal): Promise<T[]> {
  const items: T[] = [];
  let pagina = 1;
  let total: number;
  do {
    const res = await apiFetch<{ items: T[]; total: number }>(path, { params: { ...params, pagina, por_pagina: 100 }, signal });
    if (signal?.aborted) throw new DOMException("Consulta cancelada", "AbortError");
    items.push(...res.items);
    total = res.total;
    if (!res.items.length && items.length < total) throw new Error("No se pudo completar el listado. Vuelve a intentarlo.");
    pagina += 1;
  } while (items.length < total);
  return items;
}
