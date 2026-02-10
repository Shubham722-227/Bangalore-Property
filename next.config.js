/** @type {import('next').NextConfig} */
const nextConfig = {
  trailingSlash: false,
  // Include SQLite DB in serverless bundle so /api/properties and /api/auctions can read it on Vercel
  experimental: {
    outputFileTracingIncludes: {
      '/api/properties': ['./data/banglprop.db'],
      '/api/auctions': ['./data/banglprop.db'],
    },
  },
};

module.exports = nextConfig;
