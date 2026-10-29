import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { CheckCircle2, ShieldCheck, XCircle } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { AuditLogEntry, AuditVerifyResult, ModelPassport, ScorecardRun, VerifyResult } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export default function Governance() {
  return (
    <div className="mx-auto max-w-4xl p-4">
      <Tabs defaultValue="verifier">
        <TabsList>
          <TabsTrigger value="verifier">Evidence Verifier</TabsTrigger>
          <TabsTrigger value="audit">Audit Records</TabsTrigger>
          <TabsTrigger value="passport">Model Passport</TabsTrigger>
        </TabsList>
        <TabsContent value="verifier"><VerifierTab /></TabsContent>
        <TabsContent value="audit"><AuditTab /></TabsContent>
        <TabsContent value="passport"><PassportTab /></TabsContent>
      </Tabs>
    </div>
  )
}

function VerifierTab() {
  const [evidenceId, setEvidenceId] = useState("")
  const [result, setResult] = useState<VerifyResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function verify() {
    setError(null)
    setResult(null)
    try {
      setResult(await api.get<VerifyResult>(`/evidence/${evidenceId}/verify`))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Verification failed")
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader><CardTitle className="text-sm">Verify an evidence package</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3">
          <div className="flex gap-2">
            <Input placeholder="Evidence package ID" value={evidenceId} onChange={(e) => setEvidenceId(e.target.value)} />
            <Button onClick={verify} disabled={!evidenceId}>Verify</Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {result && (
            <div className="flex flex-col gap-2 rounded-md border border-border p-3 text-sm">
              <VerifyRow ok={result.clip_present} label="Clip file present on disk" />
              <VerifyRow ok={result.hash_matches} label="SHA-256 hash matches stored value" />
              <VerifyRow
                ok={result.ed25519_valid === true}
                label={result.ed25519_valid === null ? "Ed25519 signature — package predates signing" : "Ed25519 signature valid"}
              />
              <div className="mt-1 flex items-center gap-2">
                <span className="text-xs text-muted-foreground">Overall:</span>
                <Badge variant={result.intact ? "success" : "destructive"}>{result.intact ? "intact" : "TAMPERED"}</Badge>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function VerifyRow({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      {ok ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-destructive" />}
      <span>{label}</span>
    </div>
  )
}

function AuditTab() {
  const logQuery = useQuery({ queryKey: ["audit-log"], queryFn: () => api.get<AuditLogEntry[]>("/audit?limit=200") })
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null)

  async function verifyChain() {
    try {
      setVerifyResult(await api.get<AuditVerifyResult>("/audit/verify"))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to verify audit chain")
    }
  }

  if (logQuery.isError) {
    return <p className="p-4 text-sm text-muted-foreground">Your role does not have access to the audit trail.</p>
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <Button size="sm" variant="outline" onClick={verifyChain}><ShieldCheck className="h-4 w-4" /> Verify hash chain</Button>
        {verifyResult && (
          <Badge variant={verifyResult.intact ? "success" : "destructive"}>
            {verifyResult.intact ? `Chain intact (${verifyResult.total_entries} entries)` : `Broken at entry #${verifyResult.first_tampered_id}`}
          </Badge>
        )}
      </div>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-xs">
          <thead className="bg-muted/40 text-muted-foreground">
            <tr>
              <th className="px-2 py-1.5">Time</th>
              <th className="px-2 py-1.5">Actor</th>
              <th className="px-2 py-1.5">Action</th>
              <th className="px-2 py-1.5">Hash</th>
            </tr>
          </thead>
          <tbody>
            {(logQuery.data ?? []).map((entry) => (
              <tr key={entry.id} className="border-t border-border">
                <td className="px-2 py-1.5 whitespace-nowrap">{new Date(entry.timestamp).toLocaleString()}</td>
                <td className="px-2 py-1.5">{entry.actor_id ?? "system"}</td>
                <td className="px-2 py-1.5">{entry.action}</td>
                <td className="px-2 py-1.5 font-mono">{entry.entry_hash.slice(0, 10)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function PassportTab() {
  const passportQuery = useQuery({
    queryKey: ["passport"],
    queryFn: () => api.get<{ passport: ModelPassport; scorecard_runs: ScorecardRun[] }>("/passport"),
  })
  const passport = passportQuery.data?.passport
  const runs = passportQuery.data?.scorecard_runs ?? []

  if (!passport) return <p className="p-4 text-sm text-muted-foreground">Loading…</p>

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader><CardTitle className="text-sm">{passport.model_name} — {passport.model_version}</CardTitle></CardHeader>
        <CardContent className="flex flex-col gap-3 text-sm">
          <p><span className="font-medium">Task: </span>{passport.task}</p>
          <p><span className="font-medium">Training data: </span>{passport.training_data}</p>
          <p><span className="font-medium">Tracking: </span>{passport.tracking}</p>
          <div>
            <p className="mb-1 font-medium">Known limitations</p>
            <ul className="list-inside list-disc text-muted-foreground">
              {passport.known_limitations.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
          <div>
            <p className="mb-1 font-medium">Explicitly excluded capabilities</p>
            <ul className="list-inside list-disc text-muted-foreground">
              {passport.excluded_capabilities.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle className="text-sm">Measured performance scorecard</CardTitle></CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No scenario replay runs recorded yet. Run the deterministic test suite to populate this.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr><th className="py-1">Scenario</th><th className="py-1">Precision</th><th className="py-1">Recall</th><th className="py-1">Avg latency</th><th className="py-1">Run at</th></tr>
                </thead>
                <tbody>
                  {runs.map((r) => (
                    <tr key={r.id} className="border-t border-border">
                      <td className="py-1.5">{r.scenario_id}</td>
                      <td className="py-1.5">{(r.precision * 100).toFixed(0)}%</td>
                      <td className="py-1.5">{(r.recall * 100).toFixed(0)}%</td>
                      <td className="py-1.5">{r.avg_latency_ms.toFixed(0)} ms</td>
                      <td className="py-1.5">{new Date(r.run_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
