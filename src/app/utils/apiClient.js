"use client"
import useSWR from 'swr'

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8080"

const fetcher = async (url) => {
  const res = await fetch(url)

  if (!res.ok) {
    const error = new Error('An error occurred while fetching the data.')
    error.info = await res.json()
    error.statusCode = res.status
    throw error
  }

  return res.json()
}

export default function useApiGetRequest(path) {
  const endpoint = path.startsWith('/') ? path.slice(1) : path
  const url = `${API_BASE_URL}/${endpoint}`
  return useSWR(url, fetcher)
}
