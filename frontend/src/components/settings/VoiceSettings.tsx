"use client";

/** Settings > Voice — paste up to five samples of your own writing; Claude
 *  extracts a style profile that every outreach message is then written in.
 *
 *  Only the extracted PROFILE reaches outreach prompts, never the samples, so
 *  a line from a private email pasted here can never land in a prospect's
 *  inbox. The form says so, because it is the first thing a careful user
 *  will wonder before pasting a real email. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";

import {
  clearStyleProfile,
  getStyleProfile,
  saveStyleProfile,
  type StyleProfile,
} from "@/lib/api/personalization";
import { MAX_SAMPLES, formalityLabel, sampleError } from "@/lib/personalization";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function VoiceSettings() {
  const toast = useToast();
  const qc = useQueryClient();
  const query = useQuery({ queryKey: ["style-profile"], queryFn: getStyleProfile });
  const [samples, setSamples] = useState<string[]>([""]);
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    if (query.data && !touched) {
      setSamples(query.data.samples.length ? query.data.samples : [""]);
    }
  }, [query.data, touched]);

  const save = useMutation({
    mutationFn: () => saveStyleProfile(samples.map((s) => s.trim()).filter(Boolean)),
    onSuccess: (data) => {
      qc.setQueryData(["style-profile"], data);
      setTouched(false);
      toast("Voice profile saved — new outreach is written in it", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const clear = useMutation({
    mutationFn: clearStyleProfile,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["style-profile"] });
      setSamples([""]);
      setTouched(false);
      toast("Voice profile removed", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const error = touched ? sampleError(samples) : null;
  const update = (i: number, value: string) => {
    setTouched(true);
    setSamples((s) => s.map((x, j) => (j === i ? value : x)));
  };

  return (
    <AsyncState isLoading={query.isLoading} error={query.error}>
      <div className="grid gap-4 lg:grid-cols-[1fr_20rem]">
        <Card>
          <CardHeader>
            <CardTitle>Your writing voice</CardTitle>
            <p className="text-sm text-muted-foreground">
              Paste up to {MAX_SAMPLES} things you have written — emails, LinkedIn posts. We extract
              how you write (tone, formality, sentence length, humour) and every outreach message,
              follow-up and call script is written in that voice. The samples themselves are never
              used in outreach.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            {samples.map((sample, i) => (
              <div key={i} className="flex gap-2">
                <Textarea
                  aria-label={`Writing sample ${i + 1}`}
                  rows={4}
                  maxLength={4000}
                  placeholder={i === 0 ? "Paste an email or post you wrote…" : "Another sample (optional)"}
                  value={sample}
                  onChange={(e) => update(i, e.target.value)}
                />
                {samples.length > 1 && (
                  <Button variant="ghost" size="sm" aria-label={`Remove sample ${i + 1}`}
                          onClick={() => { setTouched(true); setSamples((s) => s.filter((_, j) => j !== i)); }}>
                    <Trash2 size={14} aria-hidden="true" />
                  </Button>
                )}
              </div>
            ))}
            {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
            <div className="flex flex-wrap justify-between gap-2">
              <Button variant="ghost" size="sm" disabled={samples.length >= MAX_SAMPLES}
                      onClick={() => { setTouched(true); setSamples((s) => [...s, ""]); }}>
                <Plus size={14} aria-hidden="true" /> Add sample
              </Button>
              <div className="flex gap-2">
                {query.data?.profile && (
                  <Button variant="ghost" size="sm" disabled={clear.isPending}
                          onClick={() => clear.mutate()}>
                    Remove profile
                  </Button>
                )}
                <Button size="sm" disabled={save.isPending || !!sampleError(samples)}
                        onClick={() => save.mutate()}>
                  {save.isPending ? "Analysing…" : query.data?.profile ? "Re-analyse" : "Analyse my voice"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
        <ProfileCard profile={query.data?.profile ?? null} updatedAt={query.data?.updated_at ?? null} />
      </div>
    </AsyncState>
  );
}

function ProfileCard({ profile, updatedAt }: { profile: StyleProfile | null; updatedAt: string | null }) {
  return (
    <Card>
      <CardHeader><CardTitle className="text-sm">Current profile</CardTitle></CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!profile ? (
          <p className="text-muted-foreground">
            None yet. Until you add one, outreach is written in a neutral, professional voice.
          </p>
        ) : (
          <>
            <p>{profile.summary}</p>
            <div className="flex flex-wrap gap-1.5">
              <Badge>{profile.tone}</Badge>
              <Badge>{formalityLabel(profile.formality)}</Badge>
              <Badge>{profile.vocabulary_level} vocabulary</Badge>
              <Badge>{profile.sentence_length} sentences</Badge>
              <Badge>humour: {profile.humor}</Badge>
            </div>
            {profile.do.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground">Keeps</p>
                <ul className="list-disc pl-5">{profile.do.map((d, i) => <li key={i}>{d}</li>)}</ul>
              </div>
            )}
            {profile.dont.length > 0 && (
              <div>
                <p className="text-xs font-medium text-muted-foreground">Avoids</p>
                <ul className="list-disc pl-5">{profile.dont.map((d, i) => <li key={i}>{d}</li>)}</ul>
              </div>
            )}
            {updatedAt && (
              <p className="text-xs text-muted-foreground">
                Updated {new Date(updatedAt).toLocaleString()}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
