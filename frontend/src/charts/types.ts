import type { ChartData } from "../api/types";

export type ChartItem = NonNullable<ChartData["items"]>[number];
