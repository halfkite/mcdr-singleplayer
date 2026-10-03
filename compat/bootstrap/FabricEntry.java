package io.github.mcdrsingleplayer.bootstrap;

import net.fabricmc.api.ModInitializer;

public final class FabricEntry implements ModInitializer {
    @Override public void onInitialize() {
        try {
            ((ModInitializer) Class.forName(VersionSelector.implementation() + ".SingleplayerBridge")
                .getDeclaredConstructor().newInstance()).onInitialize();
        } catch (ReflectiveOperationException exception) { throw new IllegalStateException("MCDR version adapter failed", exception); }
    }
}
