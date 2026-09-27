/** Системные настройки: нормы сроков и пороги предупреждений. */
import { useQuery } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { getSettings, saveSettings } from "../../api/endpoints";
import { useApiMutation } from "../../api/mutations";
import { invalidateInteractionData, keys, queryClient } from "../../api/queries";
import { Button, Card, ErrorState, Loading, PageHeader, TextField } from "../../components/ui";
import { usePageTitle } from "../../lib/usePageTitle";

export default function SettingsPage() {
  const settings = useQuery({ queryKey: keys.settings, queryFn: getSettings });
  const [values, setValues] = useState<Record<string, string>>({});
  usePageTitle("Настройки");

  useEffect(() => {
    if (settings.data) setValues(Object.fromEntries(settings.data.map((item) => [item.key, String(item.value)])));
  }, [settings.data]);

  const save = useApiMutation(
    () => saveSettings(Object.fromEntries(Object.entries(values).map(([key, value]) => [key, Number(value)]))),
    {
      success: "Настройки сохранены",
      onSuccess: (saved) => {
        queryClient.setQueryData(keys.settings, saved);
        invalidateInteractionData();
      },
    },
  );

  if (settings.isPending)
    return (
      <div className="page">
        <Loading />
      </div>
    );
  if (settings.isError)
    return (
      <div className="page">
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      </div>
    );

  const invalid = settings.data.some((item) => {
    const value = Number(values[item.key]);
    return !Number.isInteger(value) || value < item.minimum || value > item.maximum;
  });
  const changed = settings.data.some((item) => String(item.value) !== values[item.key]);

  return (
    <div className="page">
      <PageHeader title="Настройки" />
      <Card
        footer={
          <>
            <Button
              variant="ghost"
              icon={RotateCcw}
              onClick={() => setValues(Object.fromEntries(settings.data.map((item) => [item.key, String(item.default)])))}
            >
              Значения по умолчанию
            </Button>
            <Button icon={Save} disabled={!changed || invalid} loading={save.isPending} onClick={() => save.mutate(undefined)}>
              Сохранить
            </Button>
          </>
        }
      >
        <div className="form-grid">
          {settings.data.map((item) => {
            const value = Number(values[item.key]);
            const error =
              values[item.key] !== undefined && (!Number.isInteger(value) || value < item.minimum || value > item.maximum)
                ? `От ${item.minimum} до ${item.maximum}`
                : undefined;
            return (
              <TextField
                key={item.key}
                label={item.title}
                type="number"
                min={item.minimum}
                max={item.maximum}
                value={values[item.key] ?? ""}
                onChange={(next) => setValues((current) => ({ ...current, [item.key]: next }))}
                error={error}
                hint={`${item.description} По умолчанию ${item.default}.`}
              />
            );
          })}
        </div>
      </Card>
    </div>
  );
}
