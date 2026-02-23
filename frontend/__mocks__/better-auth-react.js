/**
 * Mock for better-auth/react in Jest tests.
 *
 * The real better-auth package ships ESM (.mjs) which Jest can't handle
 * without additional configuration. This mock provides the createAuthClient
 * function used by lib/auth/client.ts.
 */

const React = require('react')

function createAuthClient() {
  return {
    useSession: () => ({
      data: null,
      isPending: false,
      error: null,
    }),
    signIn: {
      email: async () => ({ data: null, error: null }),
      social: async () => ({ data: null, error: null }),
    },
    signUp: {
      email: async () => ({ data: null, error: null }),
    },
    signOut: async () => ({ data: null, error: null }),
    getSession: async () => ({ data: null, error: null }),
    forgetPassword: async () => ({ data: null, error: null }),
  }
}

module.exports = { createAuthClient }
