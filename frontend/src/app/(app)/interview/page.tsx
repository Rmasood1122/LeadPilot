"use client";

/** Monthly style interview: answer by typing or by dictation, review what
 *  LeadPilot learned, edit it, and only then apply it. */
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  applyInterview, discardInterview, finishInterview, getInterview, getInterviewStatus,
  saveAnswers, snoozeInterview, startInterview, type Interview,
} from "@/lib/api/interview";
import {
  FORMALITY_LABEL, MAX_ANSWER_CHARS, MIN_ANSWER_CHARS, MIN_USABLE_ANSWERS, SNOOZE_DAYS, VOICE_NOTICE,
  appendTranscript, canFinish, formToProfile, interviewErrorMessage, profileToForm, speechCtor,
  speechSupported, usableAnswers, type ProfileForm,
} from "@/lib/interview";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

export default function InterviewPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["interview-status"], queryFn: getInterviewStatus });
  const [iv, setIv] = useState<Interview | null>(null);
  const [mode, setMode] = useState<"text" | "voice">("text");
  const [ack, setAck] = useState(false);
  const [answers, setAnswers] = useState<string[]>([]);
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<ProfileForm | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recRef = useRef<any>(null);
  const questions = status.data?.questions ?? [];
  const canSpeak = typeof window !== "undefined" && speechSupported(window);

  // Resume an interview that was left open.
  useEffect(() => {
    const id = status.data?.open_interview_id;
    if (!id || iv) return;
    getInterview(id).then((r) => load(r)).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.data?.open_interview_id]);

  function load(r: Interview) {
    setIv(r);
    setMode(r.mode);
    const a = questions.map(() => "");
    r.answers.forEach((x) => { if (x.index < a.length) a[x.index] = x.text; });
    setAnswers(a);
    if (r.proposed_profile) setForm(profileToForm(r.proposed_profile));
  }
  useEffect(() => {
    if (iv && answers.length !== questions.length) setAnswers(questions.map((_, i) => answers[i] ?? ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questions.length]);

  const fail = (e: unknown) => setErr(interviewErrorMessage(e));
  const start = useMutation({
    mutationFn: () => startInterview(mode, ack),
    onSuccess: (r) => { setErr(null); load(r); qc.invalidateQueries({ queryKey: ["interview-status"] }); },
    onError: fail,
  });
  const finish = useMutation({
    mutationFn: async () => {
      if (!iv) throw new Error("no interview");
      await saveAnswers(iv.id, answers.map((text, index) => ({ index, text })).filter((a) => a.text.trim()));
      return finishInterview(iv.id);
    },
    onSuccess: (r) => { setErr(null); setIv(r); if (r.proposed_profile) setForm(profileToForm(r.proposed_profile)); },
    onError: fail,
  });
  const apply = useMutation({
    mutationFn: () => applyInterview(iv!.id, iv!.proposed_profile && form ? formToProfile(iv!.proposed_profile, form) : undefined),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["interview-status"] }); router.replace("/profile"); },
    onError: fail,
  });
  const discard = useMutation({
    mutationFn: () => discardInterview(iv!.id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["interview-status"] }); router.replace("/profile"); },
    onError: fail,
  });
  const later = useMutation({
    mutationFn: () => snoozeInterview(SNOOZE_DAYS),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["interview-status"] }); router.replace("/profile"); },
  });

  function toggleDictation() {
    if (listening) { recRef.current?.stop(); return; }
    const Ctor = speechCtor(window);
    if (!Ctor) return;
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = false;
    rec.lang = navigator.language || "en-US";
    rec.onresult = (ev: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => {
      let chunk = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) if (ev.results[i].isFinal) chunk += ev.results[i][0].transcript + " ";
      if (chunk) setAnswers((prev) => prev.map((a, i) => (i === step ? appendTranscript(a, chunk).slice(0, MAX_ANSWER_CHARS) : a)));
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recRef.current = rec;
    rec.start();
    setListening(true);
  }
  useEffect(() => () => recRef.current?.stop?.(), []);

  if (status.isLoading) return <p className="p-6 text-sm">Loading…</p>;
  if (status.isError) return <p className="p-6 text-sm">Could not load the interview.</p>;

  // ---- Step 0: choose how --------------------------------------------------
  if (!iv) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 p-4 md:p-6">
        <h1 className="text-xl font-semibold">Your monthly voice interview</h1>
        <p className="text-sm text-muted-foreground">
          Answer {questions.length} short questions, by typing or by talking. LeadPilot learns how you
          write and speak, then proposes a style. <strong>Nothing changes in your messages until you
          review it and click Apply.</strong>
        </p>
        <Card><CardContent className="space-y-3 pt-6 text-sm">
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2">
              <input type="radio" name="mode" checked={mode === "text"} onChange={() => setMode("text")} /> Text interview
            </label>
            <label className={`flex items-center gap-2 ${canSpeak ? "" : "opacity-50"}`}>
              <input type="radio" name="mode" disabled={!canSpeak} checked={mode === "voice"} onChange={() => setMode("voice")} />
              Voice interview
            </label>
          </div>
          {!canSpeak && <p className="text-xs text-muted-foreground">Voice needs Chrome, Edge or Safari. This browser can only do the text interview.</p>}
          {mode === "voice" && (
            <div className="space-y-2 rounded border p-3">
              <p className="text-xs">{VOICE_NOTICE}</p>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} /> I understand
              </label>
            </div>
          )}
          {err && <p role="alert" className="text-red-600">{err}</p>}
          <div className="flex flex-wrap gap-2">
            <Button disabled={start.isPending || (mode === "voice" && !ack)} onClick={() => start.mutate()}>Start</Button>
            <Button variant="outline" disabled={later.isPending} onClick={() => later.mutate()}>Remind me in {SNOOZE_DAYS} days</Button>
          </div>
        </CardContent></Card>
      </div>
    );
  }

  // ---- Review a proposal ---------------------------------------------------
  if (iv.status === "proposed" && iv.proposed_profile && form) {
    return (
      <div className="mx-auto max-w-2xl space-y-4 p-4 md:p-6">
        <h1 className="text-xl font-semibold">Here is what LeadPilot learned</h1>
        <p className="text-sm text-muted-foreground">Edit anything that is not you. Applying makes every message LeadPilot drafts for you follow this style.</p>
        <Card><CardHeader><CardTitle>Your style</CardTitle></CardHeader><CardContent className="space-y-3">
          <div><Label htmlFor="f-tone">Tone</Label>
            <Input id="f-tone" value={form.tone} onChange={(e) => setForm({ ...form, tone: e.target.value })} /></div>
          <div><Label htmlFor="f-form">Formality: {form.formality}/5 ({FORMALITY_LABEL[form.formality] ?? ""})</Label>
            <input id="f-form" type="range" min={1} max={5} value={form.formality}
                   onChange={(e) => setForm({ ...form, formality: Number(e.target.value) })} /></div>
          <div><Label htmlFor="f-greet">How you greet</Label>
            <Input id="f-greet" value={form.greeting_style} onChange={(e) => setForm({ ...form, greeting_style: e.target.value })} /></div>
          <div><Label htmlFor="f-sign">How you sign off</Label>
            <Input id="f-sign" value={form.signoff_style} onChange={(e) => setForm({ ...form, signoff_style: e.target.value })} /></div>
          <div><Label htmlFor="f-do">Do (one per line)</Label>
            <textarea id="f-do" className="w-full rounded border bg-background p-2 text-sm" rows={3} value={form.do} onChange={(e) => setForm({ ...form, do: e.target.value })} /></div>
          <div><Label htmlFor="f-dont">Avoid (one per line)</Label>
            <textarea id="f-dont" className="w-full rounded border bg-background p-2 text-sm" rows={3} value={form.dont} onChange={(e) => setForm({ ...form, dont: e.target.value })} /></div>
          <div><Label htmlFor="f-sum">Summary</Label>
            <textarea id="f-sum" className="w-full rounded border bg-background p-2 text-sm" rows={2} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></div>
        </CardContent></Card>
        {iv.recommendations.length > 0 && (
          <Card><CardHeader><CardTitle>Recommendations</CardTitle></CardHeader><CardContent>
            <ul className="list-disc space-y-1 pl-5 text-sm">{iv.recommendations.map((r) => <li key={r}>{r}</li>)}</ul>
          </CardContent></Card>
        )}
        {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
        <div className="flex flex-wrap gap-2">
          <Button disabled={apply.isPending} onClick={() => apply.mutate()}>Apply to my messages</Button>
          <Button variant="outline" disabled={discard.isPending} onClick={() => discard.mutate()}>Discard</Button>
        </div>
        <p className="text-xs text-muted-foreground">Your raw answers are deleted when you apply or discard.</p>
      </div>
    );
  }

  // ---- Answer the questions -----------------------------------------------
  const usable = usableAnswers(answers);
  return (
    <div className="mx-auto max-w-2xl space-y-4 p-4 md:p-6">
      <h1 className="text-xl font-semibold">Question {step + 1} of {questions.length}</h1>
      <Card><CardContent className="space-y-3 pt-6">
        <p className="font-medium">{questions[step]}</p>
        <textarea className="w-full rounded border bg-background p-2 text-sm" rows={6} aria-label={`Answer ${step + 1}`}
                  maxLength={MAX_ANSWER_CHARS} value={answers[step] ?? ""}
                  onChange={(e) => setAnswers((prev) => prev.map((a, i) => (i === step ? e.target.value : a)))} />
        <p className="text-xs text-muted-foreground">
          {(answers[step] ?? "").trim().length < MIN_ANSWER_CHARS ? `Write at least ${MIN_ANSWER_CHARS} characters for this to count. ` : ""}
          {usable} of {MIN_USABLE_ANSWERS} needed answers done.
        </p>
        {mode === "voice" && canSpeak && (
          <Button variant="outline" onClick={toggleDictation}>{listening ? "Stop dictating" : "Dictate answer"}</Button>
        )}
        {err && <p role="alert" className="text-sm text-red-600">{err}</p>}
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={step === 0} onClick={() => { recRef.current?.stop?.(); setStep(step - 1); }}>Back</Button>
          {step < questions.length - 1
            ? <Button onClick={() => { recRef.current?.stop?.(); setStep(step + 1); }}>Next</Button>
            : null}
          <Button disabled={!canFinish(answers) || finish.isPending} onClick={() => finish.mutate()}>
            {finish.isPending ? "Analysing…" : "Finish and see my style"}
          </Button>
        </div>
      </CardContent></Card>
    </div>
  );
}
