import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Plus, Trash2 } from "lucide-react"
import { api } from "@/lib/api"
import type { Camera, SOP, Schedule, Zone } from "@/lib/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Textarea } from "@/components/ui/textarea"
import ZonePolygonEditor from "@/components/ZonePolygonEditor"

const DAYS: { key: string; label: string }[] = [
  { key: "Mon", label: "Mon" }, { key: "Tue", label: "Tue" }, { key: "Wed", label: "Wed" },
  { key: "Thu", label: "Thu" }, { key: "Fri", label: "Fri" }, { key: "Sat", label: "Sat" }, { key: "Sun", label: "Sun" },
]

// The frame size every camera is resized to server-side (backend/pipeline/video_source.py).
const FRAME_WIDTH = 1280
const FRAME_HEIGHT = 720

export default function Configuration() {
  return (
    <div className="mx-auto max-w-5xl p-4">
      <Tabs defaultValue="cameras">
        <TabsList>
          <TabsTrigger value="cameras">Cameras</TabsTrigger>
          <TabsTrigger value="zones">Zones</TabsTrigger>
          <TabsTrigger value="schedules">Schedules</TabsTrigger>
          <TabsTrigger value="sops">SOPs</TabsTrigger>
        </TabsList>
        <TabsContent value="cameras"><CamerasTab /></TabsContent>
        <TabsContent value="zones"><ZonesTab /></TabsContent>
        <TabsContent value="schedules"><SchedulesTab /></TabsContent>
        <TabsContent value="sops"><SopsTab /></TabsContent>
      </Tabs>
    </div>
  )
}

function useCameras() {
  return useQuery({ queryKey: ["cameras"], queryFn: () => api.get<Camera[]>("/cameras") })
}

// ── Cameras ─────────────────────────────────────────────────────────────────

type SourceType = "video" | "dashcam" | "cctv"

const SOURCE_TYPE_META: Record<SourceType, { label: string; fieldLabel: string; placeholder: string; hint: string }> = {
  video: {
    label: "Video file",
    fieldLabel: "File path",
    placeholder: "media/test.mp4",
    hint: "A video file under ./media — loops continuously, behaves like a live feed.",
  },
  dashcam: {
    label: "Dashcam / USB camera",
    fieldLabel: "Device index",
    placeholder: "0",
    hint: "The device index of a connected camera — 0 for the first camera, 1 for the second, and so on.",
  },
  cctv: {
    label: "CCTV connection",
    fieldLabel: "RTSP URL",
    placeholder: "rtsp://192.168.1.10:554/stream",
    hint: "The RTSP stream URL for a networked CCTV/IP camera.",
  },
}

function CamerasTab() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [sourceType, setSourceType] = useState<SourceType>("video")
  const [form, setForm] = useState({ name: "", source_uri: "" })

  const camerasQuery = useCameras()
  const createMutation = useMutation({
    mutationFn: () => api.post<Camera>("/cameras", form),
    onSuccess: () => {
      toast.success("Camera added")
      setOpen(false)
      setForm({ name: "", source_uri: "" })
      setSourceType("video")
      queryClient.invalidateQueries({ queryKey: ["cameras"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/cameras/${id}`),
    onSuccess: () => {
      toast.success("Camera removed")
      queryClient.invalidateQueries({ queryKey: ["cameras"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  const sourceMeta = SOURCE_TYPE_META[sourceType]

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Cameras</CardTitle>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="h-4 w-4" /> Add Camera</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Add Camera</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Connection type</Label>
                <Select value={sourceType} onValueChange={(v) => { setSourceType(v as SourceType); setForm({ ...form, source_uri: "" }) }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(Object.keys(SOURCE_TYPE_META) as SourceType[]).map((t) => (
                      <SelectItem key={t} value={t}>{SOURCE_TYPE_META[t].label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{sourceMeta.fieldLabel}</Label>
                <Input
                  value={form.source_uri}
                  onChange={(e) => setForm({ ...form, source_uri: e.target.value })}
                  placeholder={sourceMeta.placeholder}
                />
                <span className="text-[11px] text-muted-foreground">{sourceMeta.hint}</span>
              </div>
              <Button disabled={!form.name || !form.source_uri || createMutation.isPending} onClick={() => createMutation.mutate()}>Save</Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {(camerasQuery.data ?? []).map((cam) => (
          <div key={cam.id} className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
            <div className="flex flex-col">
              <span className="font-medium">{cam.name}</span>
              <span className="text-xs text-muted-foreground">{cam.source_uri}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="capitalize">{cam.status}</Badge>
              <Button size="icon" variant="ghost" onClick={() => deleteMutation.mutate(cam.id)}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}

// ── Zones ───────────────────────────────────────────────────────────────────

function ZonesTab() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    camera_id: "",
    name: "",
    zone_type: "restricted" as Zone["zone_type"],
    risk_level: 1,
    loitering_threshold_s: "",
    polygon: [] as [number, number][],  // 0-1 fractions from the editor
  })

  const camerasQuery = useCameras()
  const zonesQuery = useQuery({
    queryKey: ["zones", camerasQuery.data?.map((c) => c.id)],
    queryFn: async () => {
      const cameras = camerasQuery.data ?? []
      const perCamera = await Promise.all(cameras.map((c) => api.get<Zone[]>(`/cameras/${c.id}/zones`)))
      return perCamera.flat()
    },
    enabled: !!camerasQuery.data,
  })
  const cameraById = (id: number) => camerasQuery.data?.find((c) => c.id === id)

  const createMutation = useMutation({
    mutationFn: () =>
      api.post<Zone>(`/cameras/${form.camera_id}/zones`, {
        name: form.name,
        zone_type: form.zone_type,
        risk_level: form.risk_level,
        loitering_threshold_s: form.loitering_threshold_s ? Number(form.loitering_threshold_s) : null,
        // Editor produces 0-1 fractions; the backend stores pixel points on the 1280x720 frame.
        polygon_points: form.polygon.map(([x, y]) => [Math.round(x * FRAME_WIDTH), Math.round(y * FRAME_HEIGHT)]),
      }),
    onSuccess: () => {
      toast.success("Zone added")
      setOpen(false)
      setForm({ camera_id: "", name: "", zone_type: "restricted", risk_level: 1, loitering_threshold_s: "", polygon: [] })
      queryClient.invalidateQueries({ queryKey: ["zones"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: (zone: Zone) => api.del(`/cameras/${zone.camera_id}/zones/${zone.id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zones"] }),
  })

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Zones</CardTitle>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm"><Plus className="h-4 w-4" /> Add Zone</Button>
          </DialogTrigger>
          <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Add Zone</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Camera</Label>
                <Select value={form.camera_id} onValueChange={(v) => setForm({ ...form, camera_id: v, polygon: [] })}>
                  <SelectTrigger><SelectValue placeholder="Select a camera" /></SelectTrigger>
                  <SelectContent>
                    {(camerasQuery.data ?? []).map((c) => <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <ZonePolygonEditor key={form.camera_id} cameraId={form.camera_id || null} initialPolygon={form.polygon} onChange={(p) => setForm({ ...form, polygon: p })} />
              <div className="flex flex-col gap-1.5">
                <Label>Zone name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Zone type</Label>
                <Select value={form.zone_type} onValueChange={(v) => setForm({ ...form, zone_type: v as Zone["zone_type"] })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="restricted">Restricted (unauthorized entry raises an incident)</SelectItem>
                    <SelectItem value="monitored">Monitored</SelectItem>
                    <SelectItem value="safe">Safe</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Risk level (1–5)</Label>
                <Input type="number" min={1} max={5} value={form.risk_level} onChange={(e) => setForm({ ...form, risk_level: Number(e.target.value) })} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Loitering threshold override (seconds, optional)</Label>
                <Input
                  type="number"
                  min={5}
                  placeholder="Use global default"
                  value={form.loitering_threshold_s}
                  onChange={(e) => setForm({ ...form, loitering_threshold_s: e.target.value })}
                />
              </div>
              <Button disabled={!form.name || !form.camera_id || form.polygon.length < 3 || createMutation.isPending} onClick={() => createMutation.mutate()}>
                Save Zone
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {(zonesQuery.data ?? []).map((zone) => (
          <div key={zone.id} className="flex items-center justify-between rounded-md border border-border p-2.5 text-sm">
            <div className="flex flex-col">
              <span className="font-medium">{zone.name}</span>
              <span className="text-xs text-muted-foreground">
                {cameraById(zone.camera_id)?.name ?? "Unknown camera"} · loiter ≥{zone.loitering_threshold_s ?? "default"}s
              </span>
            </div>
            <div className="flex items-center gap-2">
              {zone.zone_type === "restricted" && <Badge variant="destructive">Restricted</Badge>}
              {zone.zone_type === "monitored" && <Badge variant="outline">Monitored</Badge>}
              <Button size="icon" variant="ghost" onClick={() => deleteMutation.mutate(zone)}><Trash2 className="h-4 w-4" /></Button>
            </div>
          </div>
        ))}
        {(zonesQuery.data ?? []).length === 0 && <p className="text-sm text-muted-foreground">No zones configured yet.</p>}
      </CardContent>
    </Card>
  )
}

// ── Schedules ───────────────────────────────────────────────────────────────

function SchedulesTab() {
  const camerasQuery = useCameras()
  return (
    <div className="flex flex-col gap-3">
      {(camerasQuery.data ?? []).map((cam) => <CameraScheduleCard key={cam.id} camera={cam} />)}
    </div>
  )
}

function CameraScheduleCard({ camera }: { camera: Camera }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: "Business Hours", start_time: "08:00", end_time: "18:00", days: new Set(["Mon", "Tue", "Wed", "Thu", "Fri"]) })

  const schedulesQuery = useQuery({
    queryKey: ["schedules", camera.id],
    queryFn: () => api.get<Schedule[]>(`/cameras/${camera.id}/schedules`),
  })
  const createMutation = useMutation({
    mutationFn: () =>
      api.post<Schedule>(`/cameras/${camera.id}/schedules`, {
        name: form.name,
        start_time: form.start_time,
        end_time: form.end_time,
        days_of_week: Array.from(form.days),
      }),
    onSuccess: () => {
      toast.success("Schedule added")
      setOpen(false)
      queryClient.invalidateQueries({ queryKey: ["schedules", camera.id] })
    },
    onError: (e: Error) => toast.error(e.message),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.del(`/cameras/${camera.id}/schedules/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schedules", camera.id] }),
  })

  function toggleDay(day: string) {
    setForm((f) => {
      const days = new Set(f.days)
      if (days.has(day)) days.delete(day)
      else days.add(day)
      return { ...f, days }
    })
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle className="text-sm">{camera.name}</CardTitle>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button size="sm" variant="outline"><Plus className="h-4 w-4" /> Add Schedule</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader><DialogTitle>Add Schedule — {camera.name}</DialogTitle></DialogHeader>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col gap-1.5">
                <Label>Name</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </div>
              <div className="flex items-center gap-2">
                <div className="flex flex-1 flex-col gap-1.5">
                  <Label>Start</Label>
                  <Input type="time" value={form.start_time} onChange={(e) => setForm({ ...form, start_time: e.target.value })} />
                </div>
                <div className="flex flex-1 flex-col gap-1.5">
                  <Label>End</Label>
                  <Input type="time" value={form.end_time} onChange={(e) => setForm({ ...form, end_time: e.target.value })} />
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Days</Label>
                <div className="flex flex-wrap gap-2">
                  {DAYS.map((d) => (
                    <Button key={d.key} type="button" size="sm" variant={form.days.has(d.key) ? "default" : "outline"} onClick={() => toggleDay(d.key)}>
                      {d.label}
                    </Button>
                  ))}
                </div>
              </div>
              <Button disabled={!form.name || form.days.size === 0 || createMutation.isPending} onClick={() => createMutation.mutate()}>Save</Button>
            </div>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {(schedulesQuery.data ?? []).map((s) => (
          <div key={s.id} className="flex items-center justify-between rounded-md border border-border p-2 text-xs">
            <div className="flex flex-col">
              <span className="font-medium">{s.name}</span>
              <span className="text-muted-foreground">{s.start_time}–{s.end_time} · {s.days_of_week.join(", ")}</span>
            </div>
            <Button size="icon" variant="ghost" onClick={() => deleteMutation.mutate(s.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
          </div>
        ))}
        {(schedulesQuery.data ?? []).length === 0 && (
          <span className="text-[11px] text-muted-foreground">No schedule set — this camera is monitored around the clock and never counts as after-hours.</span>
        )}
      </CardContent>
    </Card>
  )
}

// ── SOPs ────────────────────────────────────────────────────────────────────

function SopsTab() {
  const queryClient = useQueryClient()
  const sopsQuery = useQuery({ queryKey: ["sops"], queryFn: () => api.get<SOP[]>("/sops") })
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  const saveMutation = useMutation({
    mutationFn: (sop: SOP) => api.patch<SOP>(`/sops/${sop.id}`, { steps_text: drafts[sop.id] ?? sop.steps_text }),
    onSuccess: () => {
      toast.success("SOP saved")
      queryClient.invalidateQueries({ queryKey: ["sops"] })
    },
    onError: (e: Error) => toast.error(e.message),
  })

  return (
    <div className="flex flex-col gap-3">
      {(sopsQuery.data ?? []).map((sop) => (
        <Card key={sop.id}>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-sm">{sop.title}</CardTitle>
            <Button size="sm" variant="outline" onClick={() => saveMutation.mutate(sop)}>Save</Button>
          </CardHeader>
          <CardContent>
            <Textarea
              rows={4}
              defaultValue={sop.steps_text}
              onChange={(e) => setDrafts((d) => ({ ...d, [sop.id]: e.target.value }))}
            />
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
