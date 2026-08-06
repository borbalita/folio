import { useState, type FormEvent } from 'react'
import { Navigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/lib/auth'

type Mode = 'sign-in' | 'sign-up'

export function LoginPage() {
  const { status, signIn, signUp } = useAuth()
  const [mode, setMode] = useState<Mode>('sign-in')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/chat" replace />
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setMessage(null)
    setSubmitting(true)

    const result =
      mode === 'sign-in' ? await signIn(email, password) : await signUp(email, password)

    setSubmitting(false)

    if (result.error) {
      setError(result.error)
      return
    }

    if (mode === 'sign-up') {
      setMessage('Account created. You can sign in if email confirmation is disabled.')
      setMode('sign-in')
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>Document Copilot</CardTitle>
          <CardDescription>
            {mode === 'sign-in'
              ? 'Sign in with your email to continue.'
              : 'Create an account with your email.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="flex flex-col gap-4" onSubmit={onSubmit}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                autoComplete={mode === 'sign-in' ? 'current-password' : 'new-password'}
                required
                minLength={6}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </div>
            {error ? <p className="text-sm text-destructive">{error}</p> : null}
            {message ? <p className="text-sm text-muted-foreground">{message}</p> : null}
            <Button type="submit" disabled={submitting || status === 'loading'}>
              {submitting
                ? 'Please wait…'
                : mode === 'sign-in'
                  ? 'Sign in'
                  : 'Sign up'}
            </Button>
          </form>
        </CardContent>
        <CardFooter className="justify-center text-sm text-muted-foreground">
          {mode === 'sign-in' ? (
            <p>
              No account?{' '}
              <button
                type="button"
                className="text-foreground underline-offset-4 hover:underline"
                onClick={() => {
                  setMode('sign-up')
                  setError(null)
                  setMessage(null)
                }}
              >
                Sign up
              </button>
            </p>
          ) : (
            <p>
              Already have an account?{' '}
              <button
                type="button"
                className="text-foreground underline-offset-4 hover:underline"
                onClick={() => {
                  setMode('sign-in')
                  setError(null)
                  setMessage(null)
                }}
              >
                Sign in
              </button>
            </p>
          )}
        </CardFooter>
      </Card>
    </main>
  )
}
