/** Single source of truth for environment config. Never read import.meta.env elsewhere. */

function required(name: string): string {
  const value = import.meta.env[name] as string | undefined
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`)
  }
  return value
}

export const env = {
  apiBaseUrl: required('VITE_API_BASE_URL'),
  supabaseUrl: required('VITE_SUPABASE_URL'),
  supabaseAnonKey: required('VITE_SUPABASE_ANON_KEY'),
} as const
