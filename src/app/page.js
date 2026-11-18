"use client";
import ChatApp from "@/components/ChatApp";
import { RequireAuth } from "@/components/AuthProvider";
export default function Home() { return <RequireAuth>{user => <ChatApp key={user.id} userId={user.id} />}</RequireAuth>; }
